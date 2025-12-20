from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed
from django.utils import timezone
from .models import Trip
import os


class LatestTripsFeed(Feed):
    feed_type = Atom1Feed
    title = "YallaBus - أحدث رحلات الباصات"
    description = "تحديثات فورية لرحلات الباصات الجديدة في اليمن ومصر"
    language = "ar"
    
    def link(self):
        site_url = os.getenv('SITE_URL', 'https://yallabus.app').rstrip('/')
        return f"{site_url}/bus_list/"

    def items(self):
        return Trip.objects.filter(status='published').select_related(
            'from_city', 'to_city', 'operator'
        ).prefetch_related('stops').order_by('-created_at')[:50]

    def item_title(self, item):
        try:
            stops = item.stops.all().order_by('sequence')
            first_stop = stops.first()
            last_stop = stops.last()
            
            if first_stop and last_stop:
                from_name = first_stop.city.name
                to_name = last_stop.city.name
                return f"رحلة من {from_name} إلى {to_name}"
        except:
            pass
        
        # Fallback to from_city/to_city if stops don't exist
        from_name = getattr(item.from_city, 'name', 'مدينة')
        to_name = getattr(item.to_city, 'name', 'مدينة')
        return f"رحلة من {from_name} إلى {to_name}"

    def item_description(self, item):
        try:
            stops = item.stops.all().order_by('sequence')
            first_stop = stops.first()
            last_stop = stops.last()
            
            operator_name = getattr(item.operator, 'name', 'يلا باص')
            departure_time = first_stop.planned_departure.strftime('%I:%M %p') if first_stop and first_stop.planned_departure else 'غير محدد'
            price = last_stop.price_from_start if last_stop else 0
            
            return f"شركة النقل: {operator_name} | موعد الإقلاع: {departure_time} | السعر: {price} ريال"
        except Exception as e:
            return f"تفاصيل الرحلة رقم {item.id}"

    def item_link(self, item):
        site_url = os.getenv('SITE_URL', 'https://yallabus.app').rstrip('/')
        return f"{site_url}/bus_list/{item.id}"

    def item_pubdate(self, item):
        return item.created_at if item.created_at else timezone.now()
