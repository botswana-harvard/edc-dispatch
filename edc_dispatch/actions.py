from django.contrib import admin
from django.http import HttpResponseRedirect


def set_is_dispatched(modeladmin, request, queryset, **kwargs):
    """Sets is dispatched to True"""
    for qs in queryset:
        if qs.is_dispatched is False:
            qs.is_dispatched = True
            qs.return_datetime = None
            qs.save()
set_is_dispatched.short_description = "Set is_dispatched to True."


def return_dispatched_containers(modeladmin, request, queryset, **kwargs):
    selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
    return HttpResponseRedirect("/bcpp/dispatch/return/?items={0}".format(",".join(selected)))
return_dispatched_containers.short_description = "Return dispatched containers to server"
