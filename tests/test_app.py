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
    assert "Core Features" in response.text
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


def test_plugin_create_edit_delete(client):
    login(client)
    new_page = client.get("/admin/plugins/new")
    assert new_page.status_code == 200
    csrf = extract_csrf_token(new_page.text)
    source = (
        "def register(app, hooks):\n"
        "    def note(context, request):\n"
        "        context = dict(context)\n"
        "        context['plugin_footer_note'] = 'From demo_writer.'\n"
        "        return context\n"
        "    hooks.add_filter('public.before_render', note)\n"
    )
    created = client.post(
        "/admin/plugins/new",
        data={
            "name": "demo_writer",
            "version": "1.0.0",
            "description": "Created in test",
            "source": source,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert created.status_code == 303

    edit_page = client.get("/admin/plugins/demo_writer/edit")
    assert edit_page.status_code == 200
    assert "Created in test" in edit_page.text
    edit_csrf = extract_csrf_token(edit_page.text)
    updated_source = source.replace("From demo_writer.", "From demo_writer v2.")
    updated = client.post(
        "/admin/plugins/demo_writer/edit",
        data={
            "version": "1.1.0",
            "description": "Updated in test",
            "source": updated_source,
            "csrf_token": edit_csrf,
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303

    saved = client.get("/admin/plugins/demo_writer/edit")
    assert saved.status_code == 200
    assert "Updated in test" in saved.text
    assert "1.1.0" in saved.text
    assert "From demo_writer v2." in saved.text

    # Disable hello_world so this plugin's footer filter is visible
    listed = client.get("/admin/plugins")
    toggle_csrf = extract_csrf_token(listed.text)
    client.post(
        "/admin/plugins/toggle",
        data={"plugin_name": "hello_world", "csrf_token": toggle_csrf},
        follow_redirects=False,
    )
    home = client.get("/")
    assert "From demo_writer v2." in home.text

    listed = client.get("/admin/plugins")
    delete_csrf = extract_csrf_token(listed.text)
    deleted = client.post(
        "/admin/plugins/demo_writer/delete",
        data={"csrf_token": delete_csrf},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    missing = client.get("/admin/plugins/demo_writer/edit", follow_redirects=False)
    assert missing.status_code == 303
    assert "/admin/plugins" in missing.headers["location"]


def test_plugin_upload_zip(client):
    import io
    import json
    import zipfile

    login(client)
    page = client.get("/admin/plugins")
    csrf = extract_csrf_token(page.text)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "zipped_demo/plugin.json",
            json.dumps(
                {
                    "name": "zipped_demo",
                    "version": "0.2.0",
                    "description": "Uploaded via ZIP",
                    "enabled_by_default": False,
                }
            ),
        )
        zf.writestr(
            "zipped_demo/plugin.py",
            "def register(app, hooks):\n"
            "    def note(context, request):\n"
            "        context = dict(context)\n"
            "        context['plugin_footer_note'] = 'From zipped_demo.'\n"
            "        return context\n"
            "    hooks.add_filter('public.before_render', note)\n",
        )
    buf.seek(0)

    uploaded = client.post(
        "/admin/plugins/upload",
        data={"csrf_token": csrf, "enable": "on"},
        files={"file": ("zipped_demo.zip", buf.getvalue(), "application/zip")},
        follow_redirects=False,
    )
    assert uploaded.status_code == 303
    assert "/admin/plugins/zipped_demo/edit" in uploaded.headers["location"]
    home = client.get("/")
    assert "From zipped_demo." in home.text

    listed = client.get("/admin/plugins")
    delete_csrf = extract_csrf_token(listed.text)
    client.post(
        "/admin/plugins/zipped_demo/delete",
        data={"csrf_token": delete_csrf},
        follow_redirects=False,
    )


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


def test_register_subscriber(client):
    page = client.get("/register")
    assert page.status_code == 200
    csrf = extract_csrf_token(page.text)
    created = client.post(
        "/register",
        data={
            "email": "reader@example.com",
            "password": "secret12345",
            "password_confirm": "secret12345",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/"
    admin = client.get("/admin", follow_redirects=False)
    assert admin.status_code == 403


def test_admin_user_management(client):
    login(client)
    users_page = client.get("/admin/users")
    assert users_page.status_code == 200
    csrf = extract_csrf_token(users_page.text)
    created = client.post(
        "/admin/users",
        data={
            "email": "author@example.com",
            "password": "authorpass1",
            "role": "author",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    listed = client.get("/admin/users")
    assert "author@example.com" in listed.text
    assert "author" in listed.text


def test_content_scheduling(client):
    from datetime import datetime, timedelta, timezone

    login(client)
    list_response = client.get("/admin/content/post")
    csrf_token = extract_csrf_token(list_response.text)
    future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    client.post(
        "/admin/content/post",
        data={
            "title": "Future Post",
            "body": "<p>Not yet</p>",
            "status_value": "scheduled",
            "publish_at": future,
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert client.get("/posts/future-post").status_code == 404

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    edit = client.get("/admin/content/post/1/edit")
    edit_csrf = extract_csrf_token(edit.text)
    client.post(
        "/admin/content/post/1",
        data={
            "title": "Future Post",
            "body": "<p>Now live</p>",
            "status_value": "scheduled",
            "publish_at": past,
            "csrf_token": edit_csrf,
        },
        follow_redirects=False,
    )
    public = client.get("/posts/future-post")
    assert public.status_code == 200
    assert "Now live" in public.text


def test_rest_api_posts(client):
    assert client.get("/api/v1/posts").status_code == 200
    assert client.get("/api/v1/posts").json() == []

    unauthorized = client.post("/api/v1/posts", json={"title": "API Post", "status": "published"})
    assert unauthorized.status_code == 401

    login(client)
    created = client.post(
        "/api/v1/posts",
        json={
            "title": "API Post",
            "body": "<p>From API</p>",
            "status": "published",
            "excerpt": "API excerpt",
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["slug"] == "api-post"
    assert payload["status"] == "published"

    listed = client.get("/api/v1/posts")
    assert listed.status_code == 200
    assert any(item["slug"] == "api-post" for item in listed.json())

    single = client.get("/api/v1/posts/api-post")
    assert single.status_code == 200
    assert single.json()["body"] == "<p>From API</p>"

    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"

    updated = client.patch("/api/v1/posts/1", json={"title": "API Post Updated"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "API Post Updated"

    deleted = client.delete("/api/v1/posts/1")
    assert deleted.status_code == 204
    assert client.get("/api/v1/posts/api-post").status_code == 404


def test_media_json_endpoint(client):
    login(client)
    media_page = client.get("/admin/media")
    csrf = extract_csrf_token(media_page.text)
    client.post(
        "/admin/media/upload",
        data={"csrf_token": csrf},
        files={"file": ("pic.png", BytesIO(b"fakepng"), "image/png")},
        follow_redirects=False,
    )
    response = client.get("/admin/media/json")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["original_name"] == "pic.png"
    assert data[0]["url"].startswith("/uploads/")


def _enable_plugin(client, name: str):
    page = client.get("/admin/plugins")
    csrf = extract_csrf_token(page.text)
    return client.post(
        "/admin/plugins/toggle",
        data={"plugin_name": name, "csrf_token": csrf},
        follow_redirects=False,
    )


def test_theme_customizer_plugin(client):
    login(client)
    enabled = _enable_plugin(client, "theme_customizer")
    assert enabled.status_code == 303

    dash = client.get("/admin")
    assert "Appearance" in dash.text

    page = client.get("/admin/appearance")
    assert page.status_code == 200
    assert "Hero section" in page.text
    csrf = extract_csrf_token(page.text)
    saved = client.post(
        "/admin/appearance",
        data={
            "csrf_token": csrf,
            "primary_color": "#ef4444",
            "accent_color": "#22d3ee",
            "background_color": "#0b0f19",
            "card_color": "#131927",
            "text_color": "#f8fafc",
            "font_family": "Poppins",
            "hero_title": "Customized by Theme Customizer",
            "hero_subtitle": "Plugin-powered appearance settings",
            "hero_cta_text": "Join now",
            "hero_cta_url": "/register",
            "hero_handwritten": "Ship faster.",
            "custom_css": ".prose-body { font-size: 1.05rem; }",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    home = client.get("/")
    assert home.status_code == 200
    assert "Customized by Theme Customizer" in home.text
    assert "Plugin-powered appearance settings" in home.text
    assert "Join now" in home.text
    assert "--brand-500: #ef4444" in home.text


def test_maintenance_mode_plugin(client):
    login(client)
    _enable_plugin(client, "maintenance_mode")
    page = client.get("/admin/maintenance")
    assert page.status_code == 200
    csrf = extract_csrf_token(page.text)
    client.post(
        "/admin/maintenance",
        data={
            "csrf_token": csrf,
            "enabled": "on",
            "title": "Down for upgrades",
            "message": "Back soon from the maintenance plugin.",
        },
        follow_redirects=False,
    )
    # Staff still sees the site
    assert client.get("/").status_code == 200

    client.post("/logout", data={"csrf_token": extract_csrf_token(client.get("/admin").text)}, follow_redirects=False)
    blocked = client.get("/")
    assert blocked.status_code == 503
    assert "Down for upgrades" in blocked.text
    assert "Back soon from the maintenance plugin." in blocked.text


def test_reading_time_plugin(client):
    login(client)
    _enable_plugin(client, "reading_time")
    list_response = client.get("/admin/content/post")
    csrf = extract_csrf_token(list_response.text)
    body = " ".join(["word"] * 400)
    client.post(
        "/admin/content/post",
        data={
            "title": "Long Read",
            "body": body,
            "status_value": "published",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    public = client.get("/posts/long-read")
    assert public.status_code == 200
    assert "min read" in public.text


def test_cookie_consent_plugin(client):
    login(client)
    _enable_plugin(client, "cookie_consent")
    page = client.get("/admin/cookie-consent")
    assert page.status_code == 200
    csrf = extract_csrf_token(page.text)
    client.post(
        "/admin/cookie-consent",
        data={
            "csrf_token": csrf,
            "message": "Cookies help this demo site.",
            "button_label": "Accept cookies",
            "policy_url": "/pages/privacy",
        },
        follow_redirects=False,
    )
    home = client.get("/")
    assert home.status_code == 200
    assert "Cookies help this demo site." in home.text
    assert "Accept cookies" in home.text
    assert "pypress-cookie-banner" in home.text
