"""Location-related models"""
from django.db import models


class CityList(models.Model):
    city = models.CharField(max_length=16, null=False, blank=False, unique=True)
    waypoints = models.JSONField(default=list)

    def __str__(self):
        return f"{self.city} - {len(self.waypoints)} waypoint(s)"
    
    @property
    def latitude(self):
        return self.waypoints[0]['lat'] if self.waypoints else None
    
    @property
    def longitude(self):
        return self.waypoints[0]['lon'] if self.waypoints else None
    
    @property
    def coordinates(self):
        if self.waypoints:
            return f"{self.waypoints[0]['lat']}, {self.waypoints[0]['lon']}"
        return None
