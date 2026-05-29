import reflex as rx
from reflex.plugins import RadixThemesPlugin, SitemapPlugin

config = rx.Config(
    app_name="web",
    plugins=[
        SitemapPlugin(),
        RadixThemesPlugin(theme=rx.theme(appearance="dark", accent_color="iris")),
    ],
)
