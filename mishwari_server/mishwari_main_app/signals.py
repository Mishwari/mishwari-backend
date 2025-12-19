from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg
from django.db import transaction
from .models import TripReview, Bus, Driver, BusOperator, Trip
from .utils.google_indexing import notify_google_indexing
import os
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=TripReview)
def update_ratings_on_review(sender, instance, created, **kwargs):
    """Auto-update cached ratings when review is created"""
    if not created:
        return
    
    # Update Bus rating
    if instance.bus_snapshot:
        bus_reviews = TripReview.objects.filter(bus_snapshot=instance.bus_snapshot)
        avg = bus_reviews.aggregate(Avg('bus_condition_rating'))['bus_condition_rating__avg']
        instance.bus_snapshot.avg_rating = round(avg, 2) if avg else 0.00
        instance.bus_snapshot.total_reviews = bus_reviews.count()
        instance.bus_snapshot.save(update_fields=['avg_rating', 'total_reviews'])
    
    # Update Driver rating
    if instance.driver_snapshot:
        driver_reviews = TripReview.objects.filter(driver_snapshot=instance.driver_snapshot)
        avg = driver_reviews.aggregate(Avg('driver_rating'))['driver_rating__avg']
        instance.driver_snapshot.driver_rating = round(avg, 2) if avg else 0.00
        instance.driver_snapshot.total_reviews = driver_reviews.count()
        instance.driver_snapshot.save(update_fields=['driver_rating', 'total_reviews'])
    
    # Update Operator rating
    operator_reviews = TripReview.objects.filter(operator_snapshot=instance.operator_snapshot)
    avg = operator_reviews.aggregate(Avg('overall_rating'))['overall_rating__avg']
    instance.operator_snapshot.avg_rating = round(avg, 2) if avg else 0.00
    instance.operator_snapshot.total_reviews = operator_reviews.count()
    instance.operator_snapshot.save(update_fields=['avg_rating', 'total_reviews'])
    
    # Recalculate health score
    from .models import OperatorMetrics
    metrics, created = OperatorMetrics.objects.get_or_create(operator=instance.operator_snapshot)
    metrics.recalculate_health_score()





@receiver(post_save, sender=Trip)
def update_health_score_on_trip_change(sender, instance, created, **kwargs):
    """Recalculate health score when trip is cancelled and notify Google for indexing"""
    
    previous_status = getattr(instance, '_previous_status', None)
    site_url = os.getenv('SITE_URL', 'https://yallabus.app')
    trip_url = f'{site_url}/bus_list/{instance.id}'
    
    logger.info(f'[SIGNAL] Trip {instance.id} saved: status={instance.status}, previous={previous_status}, created={created}')
    
    # Auto-submit to Google when trip becomes published
    if instance.status == 'published' and previous_status != 'published':
        logger.info(f'[INDEXING] Trip {instance.id} is published (created={created}, previous={previous_status})')
        transaction.on_commit(lambda: notify_google_indexing(trip_url, 'URL_UPDATED'))
    
    # Notify Google when trip status CHANGES to cancelled
    if instance.status == 'cancelled' and previous_status != 'cancelled':
        transaction.on_commit(lambda: notify_google_indexing(trip_url, 'URL_DELETED'))
        
        from .models import OperatorMetrics
        metrics, created = OperatorMetrics.objects.get_or_create(operator=instance.operator)
        
        # Update cancellation rate
        total_trips = Trip.objects.filter(operator=instance.operator).count()
        cancelled_trips = Trip.objects.filter(operator=instance.operator, status='cancelled').count()
        
        if total_trips > 0:
            metrics.cancellation_rate = (cancelled_trips / total_trips) * 100
            metrics.save(update_fields=['cancellation_rate'])
        
        metrics.recalculate_health_score()
