from datetime import datetime
from django.db.models import get_model
from django.db.models.query import QuerySet
from edc.device.sync.exceptions import PendingTransactionError
from ..exceptions import DispatchContainerError, AlreadyReturned
from ..models import DispatchContainerRegister, DispatchItemRegister
from .base_return import BaseReturn


class ReturnController(BaseReturn):

    def get_user_container_cls(self):
        dispatch_container_cls = None
        # get the DispatchContainer instance for user's container model app_label and model
        if DispatchContainerRegister.objects.filter(producer=self.get_producer(), is_dispatched=True, return_datetime__isnull=True).exists():
            dispatch_container_register = DispatchContainerRegister.objects.filter(producer=self.get_producer(), is_dispatched=True, return_datetime__isnull=True)
            dispatch_container_cls = get_model(dispatch_container_register.app_label, dispatch_container_register.model_name)
        return dispatch_container_cls

    def get_user_container_instances_for_producer(self, using=None, **kwargs):
        """Returns a queryset of dispatched user container instances for this producer."""
        # get the DispatchContainer instance for user's container model app_label and model
        user_containers = []
        if kwargs.get('selected_container_identifiers', None):
            dispatch_container_registers = DispatchContainerRegister.objects.filter(container_identifier__in=kwargs.get('selected_container_identifiers', None),
                                                                                    producer=self.get_producer(),
                                                                                    is_dispatched=True)
        else:
            dispatch_container_registers = DispatchContainerRegister.objects.filter(producer=self.get_producer(), is_dispatched=True)
        for dispatch_container_register in dispatch_container_registers:
            user_container_cls = get_model(dispatch_container_register.container_app_label, dispatch_container_register.container_model_name)
            if user_container_cls:
                user_containers.append(user_container_cls.objects.get(**{dispatch_container_register.container_identifier_attrname: dispatch_container_register.container_identifier}))
        return user_containers

    def get_dispatch_item_instances_for_container(self, dispatch_container_register, using=None):
        """Returns a queryset of dispatched DispatchItem instances for this dispatch_container_register."""
        if not isinstance(dispatch_container_register, DispatchContainerRegister):
            raise TypeError('Attribute dispatch_container_register must be an instance of DispatchContainerRegister. Got {0}'.format(dispatch_container_register))
        return DispatchItemRegister.objects.filter(dispatch_container_register=dispatch_container_register, is_dispatched=True, return_datetime__isnull=True)

    def deregister_all_for_user_container(self, user_container, using=None):
        """Returns items in a user container and the user container, as a DispatchItemRegister, itself.

        This uses the user_container to find the DispatchContainerRegister and tries to de-register all
        related instances in DispatchItemRegister. That should also include de-registering the user_container
        from DispatchItemRegister."""
        if self.has_outgoing_transactions():
            raise PendingTransactionError('Producer \'{0}\' has pending outgoing transactions on {1}. '
                                          'Run bhp_sync first.'.format(self.get_producer_name(), self.get_using_destination()))
        if self.has_incoming_transactions():
            raise PendingTransactionError('Producer \'{1}\' has pending incoming transactions on '
                                          'this server {0}. Consume them first.'.format(self.get_using_source(), self.get_producer_name()))
        # get the dispatch_container_register using the user_container
        dispatch_container_register = self.get_dispatch_container_register(user_container)
        if not dispatch_container_register:
            raise DispatchContainerError('Failed to get DispatchContainerRegister for user container {0}.'.format(user_container))
        # all tx's are consumed so flag as no longer dispatched
        # TODO: this does not return what i expect
        if DispatchItemRegister.objects.using(using).filter(dispatch_container_register__pk=dispatch_container_register.pk):
            DispatchItemRegister.objects.using(using).filter(
                dispatch_container_register__pk=dispatch_container_register.pk,
                is_dispatched=True,
                return_datetime__isnull=True).update(
                    return_datetime=datetime.now(),
                    is_dispatched=False)
        return dispatch_container_register

    def _return_items_for_queryset(self, queryset, using=None):
        """Returns items in a queryset."""
        dispatch_container_registers = []
        for obj in queryset:
            dispatch_item_register = DispatchItemRegister.objects.using(using).get(
                item_app_label=obj._meta.app_label,
                item_model_name=obj._meta.object_name,
                item_pk=obj.pk,
                is_dispatched=True,
                return_datetime__isnull=True)
            DispatchItemRegister.objects.filter(pk=dispatch_item_register.pk).update(
                    return_datetime=datetime.now(),
                    is_dispatched=False)
            # if dispatch_item_register.dispatch_container_register:
            #    dispatch_container_registers.append(dispatch_item_register.dispatch_container_register)
        return dispatch_container_registers

    def get_dispatch_container_register(self, user_container, using=None):
        if user_container:
            if not DispatchContainerRegister.objects.using(using).filter(
                    container_pk=user_container.pk,
                    container_model_name=user_container._meta.object_name.lower(),
                    container_app_label=user_container._meta.app_label,
                    is_dispatched=True,
                    return_datetime__isnull=True).exists():
                raise DispatchContainerError('User container {0} is not registered as a "dispatched" dispatch container. Not found in DispatchContainerRegister'.format(user_container))
        return DispatchContainerRegister.objects.using(using).get(
            container_pk=user_container.pk,
            container_model_name=user_container._meta.object_name.lower(),
            container_app_label=user_container._meta.app_label,
            is_dispatched=True,
            return_datetime__isnull=True)

    def _return_by_queryset(self, queryset):
        """Returns all in a queryset registered with DispatchItemRegister after first checking transactions and dispatch items.

            If all items within the DispatchContainerRegister are returned, will return the container as well."""
        # confirm no pending transaction on the producer
        if self.has_outgoing_transactions():
            raise PendingTransactionError('Producer \'{0}\' has pending outgoing transactions. '
                                          'Run bhp_sync first.'.format(self.get_producer_name()))
        # confirm no pending transaction for this producer on the source
        if self.has_incoming_transactions():
            raise PendingTransactionError('Producer \'{0}\' has pending incoming transactions on '
                                          'this server. Consume them first.'.format(self.get_producer_name()))
        dispatch_container_registers = self._return_items_for_queryset(queryset)
        for dispatch_container_register in dispatch_container_registers:
            if not DispatchItemRegister.objects.filter(dispatch_container_register=dispatch_container_register, is_dispatched=True, return_datetime__isnull=True):
                DispatchContainerRegister.objects.filter(pk=dispatch_container_register.pk).update(is_dispatched=False, return_datetime=datetime.today())

    def _return_by_user_container(self, user_container):
        """Returns the user container and the dispatch_container_register after first checking transactions and dispatch items."""
        if not user_container:
            raise DispatchContainerError('Attribute dispatch_container may not be None.')
        # confirm dispatch container has not already been returned
        if not user_container.is_dispatched_as_container():
            raise AlreadyReturned('The user container {0} is not dispatched.'.format(user_container))
        # confirm no pending transaction on the producer
        if self.has_outgoing_transactions():
            raise PendingTransactionError('Producer \'{0}\' with settings_key \'{1}\' has pending outgoing transactions. '
                                          'Run bhp_sync first.'.format(self.get_producer_name(), self.get_using_destination()))
        # confirm no pending transaction for this producer on the source
        if self.has_incoming_transactions():
            raise PendingTransactionError('Producer \'{0}\' has pending incoming transactions on '
                                          'this server. Consume them first.'.format(self.get_producer_name()))
        # de-register all items for this user container (including the user container)
        dispatch_container_register = self.deregister_all_for_user_container(user_container)
        DispatchContainerRegister.objects.filter(pk=dispatch_container_register.pk).update(is_dispatched=False, return_datetime=datetime.today())

    def _lock_container_in_producer(self, user_container):
        dispatch_container_register = self.get_dispatch_container_register(user_container)
        self._to_json(dispatch_container_register, DispatchContainerRegister)

    def return_selected_items(self, dispatched_container_list):
        if not dispatched_container_list:
            raise TypeError('dispatched container list cannot be None')
        for user_container in self.get_user_container_instances_for_producer(selected_container_identifiers=dispatched_container_list):
            if isinstance(user_container, DispatchContainerRegister):
                raise TypeError('Expected the container model to be a user model. Got DispatchContainerRegister')
            self._lock_container_in_producer(user_container)
            self._return_by_user_container(user_container)
        return 'Containers {0}, have been returned from producer \'{1}\''.format(str(dispatched_container_list), self.get_producer_name())

    def return_dispatched_items(self, queryset=None):
        """Loops thru dispatch container instances for this producer and returns them."""
        if isinstance(queryset, QuerySet):
            self._return_by_queryset(queryset)
        else:
            for user_container in self.get_user_container_instances_for_producer():
                if isinstance(user_container, DispatchContainerRegister):
                    raise TypeError('Expected the container model to be a user model. Got DispatchContainerRegister')
                self._lock_container_in_producer(user_container)
                self._return_by_user_container(user_container)
        return 'All containers have been returned from producer \'{0}\''.format(self.get_producer_name())
