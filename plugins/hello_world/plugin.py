def register(app, hooks):
    def add_footer_note(context, request):
        context = dict(context)
        context["plugin_footer_note"] = "Powered by the hello_world plugin."
        return context

    hooks.add_filter("public.before_render", add_footer_note)
