"""Management command to remove old trips from Google index"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from mishwari_main_app.models import Trip
from mishwari_main_app.utils.google_indexing import notify_google_indexing
import os


class Command(BaseCommand):
    help = 'Remove past trips from Google index'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=2, help='Remove trips older than X days (default: 2)')

    def handle(self, *args, **options):
        site_url = os.getenv('SITE_URL', 'https://yallabus.app')
        days_ago = timezone.now().date() - timezone.timedelta(days=options['days'])
        
        old_trips = Trip.objects.filter(
            journey_date__lt=days_ago,
            status__in=['published', 'completed', 'cancelled']
        )[:200]  # Limit to 200/day to stay under rate limit
        
        total = old_trips.count()
        if total == 0:
            self.stdout.write('No old trips to remove')
            return
            
        self.stdout.write(f'Removing {total} old trips from Google index...')
        
        success = 0
        for trip in old_trips:
            trip_url = f'{site_url}/bus_list/{trip.id}'
            if notify_google_indexing(trip_url, 'URL_DELETED'):
                success += 1
        
        self.stdout.write(self.style.SUCCESS(f'Completed: {success}/{total} trips removed from index'))
