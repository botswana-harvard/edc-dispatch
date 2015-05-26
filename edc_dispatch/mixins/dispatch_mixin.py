from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import ForeignKey, ManyToManyField, OneToOneField

from edc_base.models import BaseUuidModel
from edc_device.classes import Device
from edc_sync.mixins import SyncMixin

from ..exceptions import AlreadyDispatchedContainer, AlreadyDispatchedItem, DispatchContainerError


class DispatchMixin(object):
    """Base model for all UUID models and adds dispatch methods and signals. """

    self._user_container_instance = None
    self.using = 'default'

    def is_dispatch_container_model(self):
        """Flags a model as a container model that if dispatched
        will not appear in DispatchItems, but rather in DispatchContainerRegister."""
        return False

    def ignore_for_dispatch(self):
        """Flgas a model to be ignored by the dispatch infrastructure.

        ..note:: only use this for models that exist in an app listed
                 in the settings.DISPATCH_APP_LABELS but need to be
                 ignored (which should not be very often)."""
        return False

    def include_for_dispatch(self):
        """Flgas a model to be included by the dispatch infrastructure.

        ..note:: only use this for models that do not exist in an app
                 listed in the settings.DISPATCH_APP_LABELS but need
                 to be included (which should not be very often)."""
        return False

    def is_dispatchable_model(self):
        if self.ignore_for_dispatch():
            return False
        if self._meta.app_label not in settings.DISPATCH_APP_LABELS:
            if self.include_for_dispatch():
                return True
            else:
                return False
        return True

    def dispatched_as_container_identifier_attr(self):
        """Override to return the field attrname of the
        identifier used for the dispatch container.

        Must be an field attname on the model used as a dispatch
        container, such as, household_identifier on model Household."""
        raise ImproperlyConfigured(
            'Model {0} is not configured for dispatch as a '
            'container. Missing method '
            'dispatched_as_container_identifier_attr()'.format(self._meta.object_name))

    def is_dispatched(self, using=None):
        """Returns True is the model instance is dispatched otherwise False.

        The model instance may be a container or an item within a container."""
        self.using = using or self.using
        if self.is_dispatch_container_model():
            return self.is_dispatched_as_container()
        else:
            return self.is_dispatched_as_item()

    def is_dispatched_as_container(self, using=None):
        """Determines if a model instance is dispatched as a container.

        The container is at the top of the dispatch hierarchy.

        For example: a household model instance may serve as a
        container for all household members and data."""
        self.using = using or self.using
        if self.is_dispatch_container_model():
            try:
                return self.dispatched_container_item.is_dispatched
            except AttributeError:
                return False

    @property
    def dispatched_container_item(self):
        """Returns an instance from DispatchContainerRegister
        for a dispatched container item or None.

        .. seealso::, :func:`dispatched_item`"""
        DispatchContainerRegister = apps.get_model('dispatch', 'DispatchContainerRegister')
        try:
            return DispatchContainerRegister.objects.using(self.using).get(
                container_identifier=getattr(self, self.dispatched_as_container_identifier_attr()),
                is_dispatched=True,
                return_datetime__isnull=True)
        except DispatchContainerRegister.DoesNotExist:
            return None

    def is_current_device_server(self):
        return Device().is_server

    def is_dispatched_within_user_container(self, using=None):
        """Returns True if the model class is dispatched within a
        user container.

        Using the look_up attrs defined on the model, queries
        up the relational hierarchy to the container model.

        ..note:: an item is considered dispatched if it's container
                 is dispatched. It usually is also registered as a
                 dispatched item, but as described below, this may
                 not always be true.

        For example::
            a subject_consent would be considered dispatched if
            the method on subject_consent, :func:`dispatch_container_lookup`,
            returned a lookup query string that points the subject consent to
            an instance of household that is itself dispatched. The household
            is the container. The subject consent is considered dispatched
            because it's container is dispatched. The subject consent might
            not have a corresponding DispatchItemRegister. This might happen
            if the subject_consent is created on the producer and re-synced
            with the source before the Household is returned."""
        return self.user_container_instance.is_dispatched()

    @property
    def user_container_model_cls(self):
        """Returns the model class at the top of the dispatch heirarchy."""
        user_container_model_cls = self.dispatch_container_lookup()[0]
        if isinstance(user_container_model_cls, (list, tuple)):
            user_container_model_cls = apps.get_model(
                user_container_model_cls[0], user_container_model_cls[1])
        return user_container_model_cls

    @property
    def lookup_attrs(self):
        """Returns an ordered list of attribute names split from a query_string
        where the last attribute is the field name of the model class
        at the top of the dispatch hierarchy.

        ..seealso:: :func:`user_container_model_cls`"""
        lookup_attrs = self.dispatch_container_lookup()[1]
        if not isinstance(lookup_attrs, str):
            raise TypeError('Method dispatch_container_lookup must return a (model class/tuple, list) '
                            'that points to the user container')
        return lookup_attrs.split('__')

    @property
    def does_not_exist_exceptions(self):
        """Prepares and returns a list of DoesNotExist exceptions for self and each related model."""
        return tuple(set(
            [field.related.parent_model.DoesNotExist for field in self._meta.fields
             if isinstance(field, (ForeignKey, ManyToManyField, OneToOneField))] +
            [self.DoesNotExist])
        )

    @property
    def user_container_instance(self):
        """Returns the instance of the model at the top of the dispatch
        hierarchy."""
        # if self.dispatch_container_lookup():
        lookup = None
        for attrname in self.lookup_attrs:
            try:
                # find the instance at the top of the dispatch hierarchy
                user_container_instance = lookup or self
                # ... and the attr value from the instance
                lookup = getattr(user_container_instance, attrname, None)
            except self.does_not_exist_exceptions:
                # if the foreign_key that relates to the dispatch
                # container has not been set, it is not possible
                # to determine the dispatch status. This error should
                # not be excepted.
                raise DispatchContainerError(
                    'Unable to lookup the instance for user_container '
                    '{0} on model {1}. Failed on {2}.{3}'.format(
                        self.user_container_model_cls._meta.object_name,
                        self.__class__._meta.object_name,
                        user_container_instance.__class__._meta.object_name,
                        attrname))
        return user_container_instance

    def dispatch_container_lookup(self):
        """Returns a query string in the django format.

        User must override.

        if the model has no path to the user_container, such as
        Appointment or RegisteredSubject, override like this::

            def dispatch_container_lookup(self):
                return None
        if the model does have a relational path to the
        user_container, override like this::

            def dispatch_container_lookup(self):
                return (container_model_cls, 'django__style__path__to__container')

        For example:
            with a relational structure like this::
                self
                    household_structure_member
                        household_structure
                            household.household_identifier

            where 'household' is the user container with
            identifier attr 'household_identifier',
            <self> would return something like this:
                (Household, 'household_structure_member__household_structure__household__household_identifier')
        """
        raise ImproperlyConfigured('Model {0} is not configured for dispatch. '
                                   'Missing method \'dispatch_container_lookup\''.format(self._meta.object_name))

    def _bypass_for_edit(self, using=None, update_fields=None):
        using = using or 'default'
        if using in ['default', None] and not self.bypass_for_edit_dispatched_as_item(using, update_fields):
            if not self.id:
                raise AlreadyDispatchedItem('Model {0}-{1}, although dispatched, may only be '
                                            'conditionally edited. New instances are not '
                                            'allowed.'.format(self._meta.object_name, self.pk))
            return True
        return True

    def bypass_for_edit_dispatched_as_item(self, using=None, update_fields=None):
        """Users may override to allow a model to be edited even thoug it is dispatched.

        .. warning:: avoid using this. it only allows edits. you are responsible to
                  ensure your actions will not lead to data conflicts. so it is best to also
                  limit which fields may be edited.
        """
        return False

    def is_dispatched_as_item(self, using=None, user_container=None):
        """Returns the models 'dispatched' status in model DispatchItemRegister."""
        is_dispatched = False
        if self.is_dispatchable_model():
            if self.dispatched_item(using):
                is_dispatched = True
            if not is_dispatched:
                if not self.is_dispatch_container_model():
                    # if item is not registered with DispatchItemRegister AND
                    # we are not checking on behalf of
                    # a user_container ...
                    if not is_dispatched and not user_container:
                        is_dispatched = self.is_dispatched_within_user_container(using)
                        if not isinstance(is_dispatched, bool):
                            raise TypeError('Expected a boolean as a return value from '
                                            'method is_dispatched_within_user_container(). '
                                            'Got {0}'.format(is_dispatched))
        return is_dispatched

    def dispatched_item(self, using=None):
        """Checks the DispatchItemRegister and returns the
        dispatch_item instance if one exists for this model
        instance; that is, this model instance is "dispatched".

        .. warning:: this is not the same as determining if a model
                     is dispatched within a container. To determine if
                     an instance is dispatched, use :func:`is_dispatched`.
        """
        dispatch_item = None
        using = using or 'default'
        if self.id:
            if self.is_dispatchable_model():
                DispatchItemRegister = apps.get_model('dispatch', 'DispatchItemRegister')
                try:
                    dispatch_item = DispatchItemRegister.objects.using(using).get(
                        item_app_label=self._meta.app_label,
                        item_model_name=self._meta.object_name,
                        item_pk=self.pk,
                        is_dispatched=True)
                except DispatchItemRegister.DoesNotExist:
                    pass
        return dispatch_item

    @property
    def dispatched_to(self):
        """Returns the producer name that this model instance is
        dispatched to otherwise None.
        """
        try:
            return self.dispatched_container_item.producer.name
        except AttributeError:
            return None

#     def save(self, *args, **kwargs):
#         using = kwargs.get('using')
#         update_fields = kwargs.get('update_fields') or None
#         if self.id:
#             if self.is_dispatchable_model():
#                 if self.is_dispatch_container_model():
#                     if not self._bypass_for_edit(using, update_fields):
#                         if self.is_dispatched_as_container(using):
#                             raise AlreadyDispatchedContainer('Model {0}-{1} is currently dispatched '
#                                                              'as a container for other dispatched '
#                                                              'items.'.format(self._meta.object_name, self.pk))
#                 if not self._bypass_for_edit(using, update_fields):
#                     if self.is_dispatched_as_item(using):
#                         raise AlreadyDispatchedItem('Model {0}-{1} is currently dispatched'.format(
#                             self._meta.object_name, self.pk))
#         super(BaseDispatchSyncUuidModel, self).save(*args, **kwargs)
