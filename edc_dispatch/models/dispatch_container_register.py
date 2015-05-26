from django.db import models
from django.core.exceptions import ValidationError
from .base_dispatch import BaseDispatch


class DispatchContainerRegister(BaseDispatch):

    container_app_label = models.CharField(max_length=35)

    container_model_name = models.CharField(max_length=35)

    container_identifier_attrname = models.CharField(max_length=35)

    container_identifier = models.CharField(max_length=35)

    container_pk = models.CharField(max_length=50)

    dispatched_using = models.CharField(max_length=35, null=True)

    dispatch_items = models.TextField(
        max_length=500,
        help_text='Dispatch items. One per line.')

    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.is_dispatched and not self.return_datetime:
            raise ValidationError('Field attribute \'return_datetime\' may not be None if \'is_dispatched\' is False.')
        if self.is_dispatched and self.return_datetime:
            raise ValidationError('Field attribute \'return_datetime\' must be None if \'is_dispatched\' is True.')
        super(DispatchContainerRegister, self).save(*args, **kwargs)

    def __unicode__(self):
        return self.container_identifier

    def is_ready(self):
        return self.is_dispatched

    def to_items(self):
        DispatchItem = models.get_model('dispatch', 'DispatchItemRegister')
        if DispatchItem.objects.filter(dispatch_container_register__pk=self.pk):
            return '<a href="/admin/dispatch/dispatchcontainerregister/?q={pk}">items</a>'.format(pk=self.pk)
        return None
    to_items.allow_tags = True

    class Meta:
        app_label = "dispatch"
        db_table = 'bhp_dispatch_dispatchcontainerregister'
        unique_together = ('container_app_label', 'container_model_name', 'container_pk')
