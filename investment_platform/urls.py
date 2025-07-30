from django.contrib import admin
from django.urls import path, include
from django.conf import settings # Import settings
from django.conf.urls.static import static # Import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # Our app's URLs are included here
    path('', include('stocks.urls')),
]

# --- ADD THIS BLOCK ---
# This is a standard pattern in Django for serving static files during development.
# It tells Django: "If we are in DEBUG mode, add special URL patterns for static files."
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)