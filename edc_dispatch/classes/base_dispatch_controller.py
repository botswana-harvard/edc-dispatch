from django.db.models.query import QuerySet
from django.db.models import get_models, get_app, get_model

from edc.lab.lab_requisition.models import BaseRequisition
from edc_sync.models import BaseSyncUuidModel
from edc_consent.models import BaseConsent

from ..exceptions import (
    AlreadyDispatchedItem, AlreadyReturnedController, DispatchError,
    DispatchContainerError, AlreadyDispatchedContainer,
    DispatchControllerNotReady, DispatchItemError
)
from ..models import DispatchContainerRegister, BaseDispatchSyncUuidModel

from .base_dispatch import BaseDispatch


class BaseDispatchController(BaseDispatch):

    def __init__(self,
                 using_source,
                 using_destination,
                 user_container_app_label,
                 user_container_model_name,
                 user_container_identifier_attrname,
                 user_container_identifier,
                 **kwargs):
        self._dispatch_item_app_label = None
        super(BaseDispatchController, self).__init__(
            using_source,
            using_destination,
            user_container_app_label,
            user_container_model_name,
            user_container_identifier_attrname,
            user_container_identifier,
            **kwargs)
        self._dispatch_list = []
        self.skip_container = kwargs.get('skip_container', False) or False

    def get_allowed_base_models(self):
        """Ensure all model classes of instances registered as dispatch
        items/dispatched as json are of this base class only.

            Called by :func:`_to_json`"""

        return [BaseDispatchSyncUuidModel]

#    def dispatch_foreign_key_instances(self, app_label):
#        """Finds foreign_key model classes other than the visit model class and exports the instances."""
#        list_models = []
#        # TODO: should only work for list models so that it does not cascade into all data
#        # TODO: this will fail for any list models as get_allowed_base_models() only returns
#                BaseDispatchSyncUuidModel
#        if not app_label:
#            raise TypeError('Parameter app_label cannot be None.')
#        app = get_app(app_label)
#        for model_cls in get_models(app):
#            # TODO: this could be wrong visit_field_name?
#            try:
#                visit_field_name = self.get_visit_model_cls(app_label, model_cls, index='name')
#                if getattr(model_cls, visit_field_name, None):
#                    for field in model_cls._meta.fields:
#                        if not field.name == visit_field_name and isinstance(field, (ForeignKey, OneToOneField)):
#                            field_cls = field.rel.to
#                            if field_cls not in list_models:
#                                list_models.append(field_cls)
#            except:
#                pass
#        logger.info('Ready to dispatch foreign keys: {0}'.format(list_models))
#        for model_cls in list_models:
#            self.dispatch_model_as_json(
#                 model_cls.objects.using(self.get_using_source()).all(),
#                 self.get_user_container_instance(),
#                 app_label=app_label
#             )

    def get_consent_models(self, app_label):
        """Returns a list of consent model classes for this app+label."""
        return self._get_models_by_base(app_label, BaseConsent)

    def get_requisition_models(self, app_label):
        """Returns a list of consent model classes for this app+label."""
        return self._get_models_by_base(app_label, BaseRequisition)

    def _get_models_by_base(self, app_label, base_class):
        """Returns a list of consent model classes for this app_label."""
        app = get_app(app_label)
        models = []
        for model_cls in get_models(app):
            if not model_cls._meta.object_name.endswith('Audit'):
                if issubclass(model_cls, base_class):
                    models.append(model_cls)
        return models

    def get_scheduled_models(self, app_label):
        """Returns a list of model classes with a foreign key to the
        visit model for the given app, excluding audit models."""
        app = get_app(app_label)
        scheduled_models = []
        for model_cls in get_models(app):
            field_name, visit_model_cls = self.get_visit_model_cls(app_label, model_cls)
            if visit_model_cls:
                if getattr(model_cls, field_name, None):
                    if not model_cls._meta.object_name.endswith('Audit'):
                        scheduled_models.append(model_cls)
        return scheduled_models

    def dispatch_model_as_json(self, model_cls, user_container):
        """Dispatch all instances of a model class.

           Args:
                user_container: instance of model used as the container. Note items may not
                                    may not be dispatched without a container.
                model_cls: a subclass of BaseSyncUuidModel"""
        model_cls_instances = model_cls.objects.all()
        if model_cls_instances:
            self.dispatch_user_items_as_json(model_cls_instances, user_container)

    def is_ready(self,):
        """Confirm this controller can still be used to dispatch -- has not returned it's items."""
        if not self.get_container_register_instance().is_ready():
            raise AlreadyReturnedController(
                'This controller has already returned it\'s items. '
                'To dispatch new items, create a new instance.')
        return True

    def verify_user_container(self, user_container):
        if not isinstance(user_container, BaseSyncUuidModel):
            raise DispatchContainerError(
                'User container must be an instance of BaseSyncUuidModel')
        if not user_container.is_dispatch_container_model():
            raise DispatchContainerError(
                'Model {0} is not configured as a dispatch container model'.format(user_container))
        cls = get_model(self.get_user_container_app_label(), self.get_user_container_model_name())
        if not cls == self.get_user_container_cls():
            raise DispatchContainerError(
                'User container is not of the correct class for this '
                'DispatchController. Expected {0}.'.format(self.get_user_container_cls()))
        if not user_container.pk == self.get_user_container_instance().pk:
            raise DispatchContainerError(
                'User container instance is not the same as the one registered '
                'with this controller. {0} != {1}.'.format(
                    user_container.pk, self.get_user_container_instance().pk))
        return True

    def dispatch_user_container_as_json(self, user_container):
        """Dispatch the user container as a "container".

        ..note:: This happens before the user container is dispatched
        as an item and before any others are dispatched as items."""
        if not user_container:
            user_container = self.get_user_container_instance()
        if self.is_ready():
            if self.verify_user_container(user_container):
                if user_container.is_dispatched_as_item():
                    if not self.get_controller_state() == 'retry':
                        raise AlreadyDispatchedContainer(
                            'Container is already dispatched as an item. Got {0}.'.format(user_container))
                else:
                    self._dispatch_as_json([user_container])
                if not self.register_with_dispatch_item_register(user_container):
                    raise DispatchError(
                        'Unable to create a dispatch item register for user '
                        'container {0} {1} to {2}.'.format(
                            user_container._meta.object_name, user_container.object, self.get_using_destination()))

    def dispatch_user_items_as_json(
            self, user_items, user_container=None,
            fk_to_skip=None, additional_base_model_class=None):
        if not user_items:
            raise DispatchItemError('Attribute \'user_items\' cannot be None.')
        user_container = user_container or self.get_user_container_instance()
        if not user_container.is_dispatched_as_item():
            raise DispatchControllerNotReady(
                'User container {0} has not yet been dispatched as an item to {1}. Dispatch the user '
                'container as an item (to json) before dispatching other items (to json)'.format(
                    user_container, self.get_using_destination()))
        if self.is_ready():
            if self.verify_user_container(user_container):
                # confirm instance type of user items
                if not isinstance(user_items, (BaseDispatchSyncUuidModel, list, QuerySet)):
                    raise DispatchItemError(
                        'Items for dispatch to json must be instances of '
                        '(BaseDispatchSyncUuidModel, list, QuerySet). Got {0}'.format(user_items))
                # confirm container is not DispatchContainerRegister
                if isinstance(user_container, DispatchContainerRegister):
                    raise DispatchContainerError(
                        'User container may not be DispatchContainerRegister. '
                        'Got {0}'.format(user_container))
                # confirm no user_items are already dispatched (but
                # send with user_container to skip the "dispatched within container" check)
                if not isinstance(user_items, (list, QuerySet)):
                    user_items = [user_items]
                cls_list = [o.__class__ for o in user_items]
                cls_list = list(set(cls_list))
                # confirm user items are of the same class
                if not len(user_items) == 0 and not len(cls_list) == 1:
                    raise DispatchItemError(
                        'User items must be of the same base model class. Got {0}'.format(cls_list))
                # confirm base class is correct
                if not issubclass(
                        cls_list[0],
                        self._get_allowed_base_models(
                            additional_base_model_class=additional_base_model_class)):
                    raise DispatchItemError('Model {0} is not a subclass of {1}'.format(
                        cls_list[0],
                        self._get_allowed_base_models(
                            additional_base_model_class=additional_base_model_class)))
                else:
                    # confirm user items and user container are NOT of the same class
                    if user_container:
                        if len(cls_list) > 0 and cls_list[0] == user_container.__class__:
                            raise DispatchContainerError(
                                'User item and User container cannot be of the same class. '
                                'Got {0}, {1}'.format(cls_list, user_container.__class__))
                    # confirm all items are of dispatchable models
                    not_dispatchable = [item for item in user_items if not item.is_dispatchable_model()]
                    if not_dispatchable:
                        raise DispatchItemError('All instances must be configured for dispatch. Found {0} '
                                                'that are not. Got {1}. See method \'is_dispatchable_model\''
                                                ''.format(len(not_dispatchable), not_dispatchable))
                    already_dispatched_items = [
                        user_instance for user_instance in user_items if user_instance.is_dispatched_as_item(using=self.get_using_source(), user_container=user_container)]
                    if already_dispatched_items:
                        raise AlreadyDispatchedItem('{0} models are already dispatched. Got {1}'.format(len(already_dispatched_items), already_dispatched_items))
                    # dispatch
                    self._dispatch_as_json(user_items, user_container=user_container, fk_to_skip=fk_to_skip)
                    # register the user items with the dispatch item register
                    for user_item in user_items:
                        if not self.register_with_dispatch_item_register(user_item, user_container):
                            raise DispatchError('Unable to create a dispatch item register instance for {0} {1} to {2}.'.format(user_item._meta.object_name, user_item, self.get_using_destination()))
                        print('  dispatched user item {0} {1} to {2}.'.format(user_item._meta.object_name, user_item, self.get_using_destination()))

    def _dispatch_as_json(self, model_instances, user_container=None, fk_to_skip=None, additional_base_model_class=None):
        """Passes on to _to_json along with a callback to consume foreignkeys.
           Bypass container_dispatch_model if self.skip_container is set True, dispatch_container_model is set True"""
        if (self.skip_container and user_container.is_dispatch_container_model() and model_instances == user_container):
            print(
                'Skipped dispatch_container_model {0} {1} to {2}.'.format(
                    user_container._meta.object_name, user_container, self.get_using_destination())
            )
        else:
            self._to_json(
                model_instances,
                user_container=user_container,
                fk_to_skip=fk_to_skip,
                additional_base_model_class=additional_base_model_class
            )
