import re
from io import BytesIO


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


def test_root_serves_public_home(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "FastAPI Powered CMS" in response.text
    assert "Latest posts" in response.text
    assert "Powered by the hello_world plugin" in response.text


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
    assert "admin@example.com" in posts_response.text

    edit_response = client.get("/admin/content/post/1/edit")
    edit_csrf = extract_csrf_token(edit_response.text)
    update_response = client.post(
        "/admin/content/post/1",
        data={
            "title": "Hello World Updated",
            "body": "Updated body",
            "excerpt": "Short excerpt",
            "meta_title": "SEO Title",
            "meta_description": "SEO Description",
            "status_value": "published",
            "csrf_token": edit_csrf,
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303

    updated_posts = client.get("/admin/content/post")
    assert "Hello World Updated" in updated_posts.text
    assert "published" in updated_posts.text

    public = client.get("/posts/hello-world")
    assert public.status_code == 200
    assert "Hello World Updated" in public.text
    assert "SEO Description" in public.text
    assert "Powered by the hello_world plugin" in public.text


def test_draft_not_public(client):
    login(client)
    list_response = client.get("/admin/content/post")
    csrf_token = extract_csrf_token(list_response.text)
    client.post(
        "/admin/content/post",
        data={
            "title": "Secret Draft",
            "body": "Hidden",
            "status_value": "draft",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    response = client.get("/posts/secret-draft")
    assert response.status_code == 404
    home = client.get("/")
    assert "Secret Draft" not in home.text


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

    public = client.get("/pages/about")
    assert public.status_code == 200
    assert "About page body" in public.text


def test_delete_post(client):
    login(client)
    list_response = client.get("/admin/content/post")
    csrf_token = extract_csrf_token(list_response.text)
    client.post(
        "/admin/content/post",
        data={
            "title": "Temp Post",
            "body": "Bye",
            "status_value": "published",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    edit = client.get("/admin/content/post/1/edit")
    delete_csrf = extract_csrf_token(edit.text)
    deleted = client.post(
        "/admin/content/post/1/delete",
        data={"csrf_token": delete_csrf},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert client.get("/posts/temp-post").status_code == 404


def test_categories_and_archive(client):
    login(client)
    tax = client.get("/admin/taxonomies")
    csrf = extract_csrf_token(tax.text)
    client.post(
        "/admin/taxonomies/categories",
        data={"name": "News", "csrf_token": csrf},
        follow_redirects=False,
    )
    tax = client.get("/admin/taxonomies")
    assert "News" in tax.text

    list_response = client.get("/admin/content/post")
    csrf_token = extract_csrf_token(list_response.text)
    client.post(
        "/admin/content/post",
        data={
            "title": "Cat Post",
            "body": "Body",
            "status_value": "published",
            "csrf_token": csrf_token,
            "category_ids": "1",
        },
        follow_redirects=False,
    )
    archive = client.get("/category/news")
    assert archive.status_code == 200
    assert "Cat Post" in archive.text


def test_media_upload(client):
    login(client)
    media_page = client.get("/admin/media")
    assert media_page.status_code == 200
    csrf = extract_csrf_token(media_page.text)
    response = client.post(
        "/admin/media/upload",
        data={"csrf_token": csrf},
        files={"file": ("hello.txt", BytesIO(b"hello media"), "text/plain")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    listed = client.get("/admin/media")
    assert "hello.txt" in listed.text
    assert "/uploads/" in listed.text


def test_themes_page(client):
    login(client)
    response = client.get("/admin/themes")
    assert response.status_code == 200
    assert "default" in response.text
    assert "Active" in response.text


def test_plugins_toggle(client):
    login(client)
    response = client.get("/admin/plugins")
    assert response.status_code == 200
    assert "hello_world" in response.text
    csrf = extract_csrf_token(response.text)
    toggled = client.post(
        "/admin/plugins/toggle",
        data={"plugin_name": "hello_world", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert toggled.status_code == 303
    home = client.get("/")
    assert "Powered by the hello_world plugin" not in home.text


def test_sitemap_and_robots(client):
    login(client)
    list_response = client.get("/admin/content/post")
    csrf_token = extract_csrf_token(list_response.text)
    client.post(
        "/admin/content/post",
        data={
            "title": "Mapped",
            "body": "Body",
            "status_value": "published",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Sitemap:" in robots.text
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "posts/mapped" in sitemap.text
