from django.db import models
from django.core.exceptions import ValidationError
from .base_dispatch import BaseDispatch
from .dispatch_container_register import DispatchContainerRegister


class DispatchItemRegister(BaseDispatch):

    dispatch_container_register = models.ForeignKey(DispatchContainerRegister)

    item_app_label = models.CharField(max_length=35)

    item_model_name = models.CharField(max_length=35)

    item_identifier_attrname = models.CharField(max_length=35)

    item_identifier = models.CharField(max_length=40)

    item_pk = models.CharField(max_length=50)

    dispatch_host = models.CharField(max_length=35, null=True)

    dispatch_using = models.CharField(max_length=35, null=True)

    registered_subjects = models.TextField(
        verbose_name='List of Registered Subjects',
        null=True,
        blank=True,
        help_text="List of Registered Subjects linked to this DispatchItem"
        )

    objects = models.Manager()

# temp removed - erikvw (fails on unknown producer when setting dispatched to False)
# no longer necessary to check if the instance is dispatched, as this is done by
# the controller class.
    def save(self, *args, **kwargs):
        """Confirms an instance does not exist for this item_identifier."""
        using = kwargs.get('using')
        if self.__class__.objects.using(using).filter(
                item_identifier=self.item_identifier,
                is_dispatched=True,
                ).exclude(pk=self.pk).exists():
            dispatch_item = self.__class__.objects.using(using).get(
                item_identifier=self.item_identifier,
                is_dispatched=True,
                ).exclude(pk=self.pk)
            raise ValueError("Cannot dispatch. The item \'{0}\' is already dispatched to \'{1}\'.".format(dispatch_item.item_identifier, dispatch_item.dispatch_container_register.producer))
        if self.is_dispatched and self.return_datetime:
            raise ValidationError('Attribute return_datetime must be None if is_dispatched=True.')
        if not self.is_dispatched and not self.return_datetime:
            raise ValidationError('Attribute \'return_datetime\' may not be None if \'is_dispatched\'=False.')

        super(DispatchItemRegister, self).save(*args, **kwargs)

    def __unicode__(self):
        return "Dispatch Item {0} {1} -> {2} ({3})".format(self.item_model_name, self.item_identifier, self.producer.name, self.is_dispatched)

    class Meta:
        app_label = "dispatch"
        db_table = 'bhp_dispatch_dispatchitemregister'
        unique_together = (('dispatch_container_register', 'item_pk', 'item_identifier', 'is_dispatched'), )
        index_together = [['item_app_label', 'item_model_name', 'item_pk', 'is_dispatched'], ]
