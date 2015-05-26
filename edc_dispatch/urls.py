from django.conf.urls import patterns, url

from .views import return_items

urlpatterns = patterns('',
    url(r'^return/', return_items),
    url(r'^return/(?P<identifier>\w+)/', 'return_households', name='return_household'),
    url(r'^return/(?P<identifier>\w+)/', 'return_households', name='return_household'),
    )
