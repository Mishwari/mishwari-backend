from django.apps import AppConfig


class MishwariMainAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mishwari_main_app'
    
    def ready(self):
        import mishwari_main_app.signals  # Register signals
