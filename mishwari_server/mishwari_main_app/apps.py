from django.apps import AppConfig


class MishwariMainAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mishwari_main_app'
    
    def ready(self):
        import sys
        sys.stdout.write('[DJANGO] MishwariMainAppConfig.ready() called - importing signals\n')
        sys.stdout.flush()
        import mishwari_main_app.signals  # Register signals
        sys.stdout.write('[DJANGO] Signals imported successfully\n')
        sys.stdout.flush()
