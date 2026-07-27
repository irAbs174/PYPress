import re


def extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def login(client):
    response = client.get("/login")
    csrf_token = extract_csrf_token(response.text)
    return client.post(
        "/login",
        data={
            "email": "admin@example.com",
            "password": "admin12345",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )


def test_root_redirects_to_admin(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_admin_requires_login(client):
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_and_logout(client):
    login_response = login(client)
    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/admin"

    dashboard_response = client.get("/admin")
    assert dashboard_response.status_code == 200
    assert "Dashboard" in dashboard_response.text

    csrf_token = extract_csrf_token(dashboard_response.text)
    logout_response = client.post(
        "/logout",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert logout_response.status_code == 303
    assert logout_response.headers["location"].startswith("/login")


def test_create_and_update_post(client):
    login(client)

    list_response = client.get("/admin/content/post")
    assert list_response.status_code == 200
    csrf_token = extract_csrf_token(list_response.text)

    create_response = client.post(
        "/admin/content/post",
        data={
            "title": "Hello World",
            "body": "First body",
            "status_value": "draft",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    posts_response = client.get("/admin/content/post")
    assert "Hello World" in posts_response.text
    assert "draft" in posts_response.text
    assert "hello-world" in posts_response.text

    edit_response = client.get("/admin/content/post/1/edit")
    edit_csrf = extract_csrf_token(edit_response.text)
    update_response = client.post(
        "/admin/content/post/1",
        data={
            "title": "Hello World Updated",
            "body": "Updated body",
            "status_value": "published",
            "csrf_token": edit_csrf,
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303

    updated_posts = client.get("/admin/content/post")
    assert "Hello World Updated" in updated_posts.text
    assert "published" in updated_posts.text


def test_create_page(client):
    login(client)
    page_list = client.get("/admin/content/page")
    csrf_token = extract_csrf_token(page_list.text)

    response = client.post(
        "/admin/content/page",
        data={
            "title": "About",
            "body": "About page body",
            "status_value": "published",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    page_list = client.get("/admin/content/page")
    assert "About" in page_list.text
    assert "published" in page_list.text
