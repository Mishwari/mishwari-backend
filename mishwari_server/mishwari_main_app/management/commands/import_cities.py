# command : python .\manage.py import_cities ./cities_list.json
import json
from django.core.management.base import BaseCommand, CommandError
from mishwari_main_app.models import CityList

class Command(BaseCommand):
    help = 'Load a list of cities from a JSON file into the database'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to the JSON file')

    def handle(self, *args, **kwargs):
        json_file_path = kwargs['json_file']
        try:
            with open(json_file_path, 'r',encoding='utf-8') as file:
                cities = json.load(file)
                for city in cities:
                    CityList.objects.get_or_create(
                        city=city['city'],
                        defaults={
                            'latitude': city['latitude'],
                            'longitude': city['longitude'],
                            'proximity': city['proximity']
                        }
                    )
            self.stdout.write(self.style.SUCCESS('Successfully added cities'))
        except FileNotFoundError:
            raise CommandError('File "{}" does not exist'.format(json_file_path))
        except json.JSONDecodeError:
            raise CommandError('Error decoding JSON from "{}"'.format(json_file_path))
