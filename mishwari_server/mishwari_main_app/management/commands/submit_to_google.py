"""Management command to submit trips to Google Indexing API"""
from django.core.management.base import BaseCommand
from mishwari_main_app.models import Trip
from mishwari_main_app.utils.google_indexing import notify_google_indexing
import os


class Command(BaseCommand):
    help = 'Submit published trips to Google Indexing API'

    def add_arguments(self, parser):
        parser.add_argument('--trip-id', type=int, help='Submit specific trip by ID')
        parser.add_argument('--all', action='store_true', help='Submit all published trips')
        parser.add_argument('--test', action='store_true', help='Test credentials only')

    def handle(self, *args, **options):
        site_url = os.getenv('SITE_URL', 'https://yallabus.app')
        
        # Test mode
        if options['test']:
            self.stdout.write('Testing Google Indexing API credentials...')
            test_url = f'{site_url}/bus_list/1'
            result = notify_google_indexing(test_url, 'URL_UPDATED')
            if result:
                self.stdout.write(self.style.SUCCESS('✓ Credentials working'))
            else:
                self.stdout.write(self.style.ERROR('✗ Credentials failed'))
            return
        
        # Single trip
        if options['trip_id']:
            try:
                trip = Trip.objects.get(id=options['trip_id'])
                trip_url = f'{site_url}/bus_list/{trip.id}'
                self.stdout.write(f'Submitting trip {trip.id}...')
                if notify_google_indexing(trip_url, 'URL_UPDATED'):
                    self.stdout.write(self.style.SUCCESS(f'✓ Trip {trip.id} submitted'))
                else:
                    self.stdout.write(self.style.ERROR(f'✗ Trip {trip.id} failed'))
            except Trip.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Trip {options["trip_id"]} not found'))
            return
        
        # All published trips
        if options['all']:
            trips = Trip.objects.filter(status='published')
            total = trips.count()
            self.stdout.write(f'Submitting {total} published trips...')
            
            success = 0
            for trip in trips:
                trip_url = f'{site_url}/bus_list/{trip.id}'
                if notify_google_indexing(trip_url, 'URL_UPDATED'):
                    success += 1
                    self.stdout.write(f'  ✓ {trip.id}')
                else:
                    self.stdout.write(f'  ✗ {trip.id}')
            
            self.stdout.write(self.style.SUCCESS(f'\nCompleted: {success}/{total} trips submitted'))
            return
        
        self.stdout.write(self.style.WARNING('Use --test, --trip-id, or --all'))
