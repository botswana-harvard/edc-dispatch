import logging
import socket
from django.conf import settings
from django.db.models import get_model, ForeignKey, OneToOneField
from django.db import IntegrityError
from django.core.exceptions import ImproperlyConfigured
from edc.subject.visit_schedule.models import MembershipForm
from ..exceptions import (DispatchModelError, DispatchError,
                          AlreadyDispatched, DispatchControllerError)
from ..models import DispatchItemRegister, DispatchContainerRegister
from .base_controller import BaseController

logger = logging.getLogger(__name__)


class NullHandler(logging.Handler):
    def emit(self, record):
        pass
nullhandler = logger.addHandler(NullHandler())


class BaseDispatch(BaseController):
    """A user model is registered as dispatched by creating an instance
    in DispatchItemRegister searchable on its pk, app_label, model_name.

    Additionally::
        * a model can be configured as a container model and registered
          with the DispatchContainerRegister.
        * All user models are registered in DispatchItemRegister, user
          containers and user items.
        * If a user model is registered as a container, other user
          models are configured to be "contained" by it.
        * If a user container is dispatched, all its items are
          considered dispatched.
        * a user model cannot be dispatched as a container if not
          configured to be a user container.
    """
    def __init__(self,
                 using_source,
                 using_destination,
                 user_container_app_label,
                 user_container_model_name,
                 user_container_identifier_attrname,
                 user_container_identifier,
                 **kwargs):
        super(BaseDispatch, self).__init__(using_source, using_destination, **kwargs)
        self._dispatch_item_model_name = None
        self._user_container_app_label = None
        self._user_container_identifier_attrname = None
        self._user_container_identifier = None
        self._user_container_instance = None
        self._user_container_cls = None
        self._dispatch = None
        self._dispatch_container_register = None
        self._visit_models = {}
        # register .. don't want multiple instances for the same producer running
        # registered_controllers.register(self, retry=kwargs.get('retry', False))
        self._set_user_container_app_label(user_container_app_label)
        self._set_user_container_model_name(user_container_model_name)
        self._set_user_container_identifier_attrname(user_container_identifier_attrname)
        self.set_user_container_identifier(user_container_identifier)

        if kwargs.get('retry', False):
            self.set_controller_state('retry')
        self.debug = kwargs.get('debug', False)

    def _repr(self):
        return 'DispatchController[{0}]'.format(self.get_producer().settings_key)

    def preload_session_container(self):
        """Loads the session container for items that are currently
        dispatched when retrying the dispatch for this user_container."""
        user_container = self.get_user_container_instance()
        # confirm user_container is dispatched
        if not user_container.is_dispatched_as_container():
            DispatchControllerError('Attempt to preload a container that has not '
                                    'been dispatched. Got {0}'.format(user_container))
        # add the container
        self.add_to_session_container(user_container, 'dispatched')
        self.add_to_session_container(user_container, 'serialized')
        # get list of dispatched items for this container and add to session container
        for dispatch_register_item in self.get_registered_items():
            item_cls = get_model(dispatch_register_item.item_app_label,
                                 dispatch_register_item.item_model_name)
            instance = item_cls.objects.get(pk=dispatch_register_item.item_pk)
            self.add_to_session_container(instance, 'dispatched')
            self.add_to_session_container(instance, 'serialized')

    def register_with_dispatch_item_register(self, instance, user_container=None):
        """Registers a user model with DispatchItemRegister."""
        # confirm is a container model if user_container=None
        if not user_container and not instance.is_dispatch_container_model():
            raise DispatchError('Instance {0} is not a container model so attribute '
                                '\'user_container\' cannot be None.'.format(instance))
        if not user_container and instance.dispatch_container_lookup():
            raise DispatchError('Instance {0} may not be dispatched without a '
                                'user container. Model method dispatch_container_'
                                'lookup() is not None'.format(instance))
        # confirm user container is registered with DispatchContainerRegister
        if user_container:
            if not user_container.is_dispatched_as_container():
                raise DispatchError('Instance {0} must be registered with a '
                                    'valid user container. Model {1} is not '
                                    'dispatched as a user container.'.format(instance, user_container))
        return self._register_item(instance, user_container)

    def _set_user_container_model_name(self, value=None):
        # if not value:
        #    raise AttributeError('The model_name of the user\'s '
        #                         'container model cannot be None.
        #                          'Set this in __init__() of the subclass.')
        self._user_container_model_name = value
        self.initialize_session_container()

    def get_user_container_model_name(self):
        """Gets the model name for the user\'s container model."""
        if not self._user_container_model_name:
            self._set_user_container_model_name()
        return self._user_container_model_name

    def _set_user_container_app_label(self, value=None):
        # if not value:
        #   raise AttributeError('The app_label of the user\'s container model '
        #                         'cannot be None. Set this in __init__() of the subclass.')
        self._user_container_app_label = value

    def get_user_container_app_label(self):
        """Gets the app_label for the user\'s container model."""
        if not self._user_container_app_label:
            self._set_user_container_app_label()
        return self._user_container_app_label

    def _set_user_container_identifier_attrname(self, value=None):
        """Sets identifier field attribute of the user\'s container
        model.

        This is an identifier for the model thats the starting point
        of dispatching e.g household_identifier if starting with
        household or subject identifier if starting with registered
        subject.

        This identifier will be determined by the application specific
        controller/model sub classing a base model e.g
        MochudiDispatchController or mochudi_household
        """
        if not value:
            raise AttributeError('The identifier field of the user\'s container '
                                 'model cannot be None. Set this in __init__() '
                                 'of the subclass.')
        self._user_container_identifier_attrname = value

    def get_user_container_identifier_attrname(self):
        """Gets the container identifier attr for the user\'s container model."""
        if not self._user_container_identifier_attrname:
            self._set_user_container_identifier_attrname()
        return self._user_container_identifier_attrname

    def set_user_container_identifier(self, value=None):
        if not value:
            raise AttributeError('The identifier of the user\'s container '
                                 'model instance cannot be None.')
        self._user_container_identifier = value

    def get_user_container_identifier(self):
        """Gets the identifier for the user's container instance."""
        if not self._user_container_identifier:
            self.set_user_container_identifier()
        return self._user_container_identifier

    def get_user_container_instance(self):
        return self.get_user_container_cls().objects.get(
            **{self.get_user_container_identifier_attrname(): self.get_user_container_identifier()})

    def _set_user_container_cls(self):
        user_container_cls = None
        if self.get_user_container_app_label() and self.get_user_container_model_name():
            user_container_cls = get_model(self.get_user_container_app_label(),
                                           self.get_user_container_model_name())
            if not user_container_cls:
                raise TypeError('Unable to get the user container class with get_model() '
                                'using {app_label:{0}, model_name:{1}}'.format(
                                    self.get_user_container_app_label(),
                                    self.get_user_container_model_name()))
        self._user_container_cls = user_container_cls

    def get_user_container_cls(self):
        """Gets the identifier for the user's container instance."""
        if not self._user_container_cls:
            self._set_user_container_cls()
        return self._user_container_cls

    def get_user_item_identifier_attrname(self):
        return 'id'

    def _set_container_register_instance(self, dispatch_container_register=None):
        """Creates a dispatch container instance for this controller session.

        This gets or creates for each instance."""
        if dispatch_container_register:
            # just requery
            self._dispatch_container_register = DispatchContainerRegister.objects.using(
                self.get_using_source()).get(pk=str(dispatch_container_register.pk))
        else:
            # confirm user's app_label and model name get a valid container model
            user_container_model = get_model(self.get_user_container_app_label(),
                                             self.get_user_container_model_name())
            if not user_container_model:
                raise DispatchModelError('Method get_model returned None trying to get the '
                                         'user_container model class using app_label={0}, '
                                         'model_name={1}'.format(self.get_user_container_app_label(),
                                                                 self.get_user_container_model_name()))
            if not user_container_model().is_dispatch_container_model():
                raise DispatchError('Model {0} cannot be used as a container. Model '
                                    'method is_dispatch_container_model() returned '
                                    'False.'.format(user_container_model))
            if not user_container_model.objects.filter(
                    **{self.get_user_container_identifier_attrname(): self.get_user_container_identifier()}):
                raise DispatchModelError('Cannot set container model instance. Container model '
                                         '{0} matching query does not exist for {1}=\'{2}\'.'.format(
                                             user_container_model._meta.object_name,
                                             self.get_user_container_identifier_attrname(),
                                             self.get_user_container_identifier()))
            # return the instance of the user\'s container model (e.g. Household)
            user_container = user_container_model.objects.using(self.get_using_source()).get(
                **{self.get_user_container_identifier_attrname(): self.get_user_container_identifier()})
            if not getattr(user_container, self.get_user_container_identifier_attrname()):
                raise DispatchError('Could not get user\'s container instance. Attribute {0} '
                                    'not found on model instance {1}.'.format(
                                        self.get_user_container_identifier_attrname(),
                                        self.get_user_container_model_name()))
            defaults = {'is_dispatched': True,
                        'return_datetime': None,
                        'container_identifier_attrname': self.get_user_container_identifier_attrname(),
                        'producer': self.get_producer(),
                        'container_identifier': getattr(
                            user_container, self.get_user_container_identifier_attrname())}
            self._dispatch_container_register, created = DispatchContainerRegister.objects.using(
                self.get_using_source()).get_or_create(
                    container_app_label=self.get_user_container_app_label(),
                    container_model_name=self.get_user_container_model_name(),
                    container_pk=user_container.pk,
                    defaults=defaults)
            if not created:
                for attrname, value in defaults.iteritems():
                    setattr(self._dispatch_container_register, attrname, value)
                self._dispatch_container_register.save(using=self.get_using_source())

    def get_container_register_instance(self):
        """Gets the dispatch container instance for this controller sessions."""
        if not self._dispatch_container_register:
            self._set_container_register_instance()
        else:
            # requery (may be called after a return controller deregistered)
            pk = self._dispatch_container_register.pk
            self._set_container_register_instance(self._dispatch_container_register)
            if not self._dispatch_container_register.pk == pk:
                raise ValueError('DispatchContainerRegister pk has changed unexpectedly.')
        return self._dispatch_container_register

    def get_dispatch_item_register_for_producer(self):
        """Returns a queryset of dispatched DispatchItemRegister model
        instances for this producer."""
        if not self._dispatch_item_register_for_producer:
            self.set_dispatch_item_register_for_producer()
        return self._dispatch_item_register_for_producer

    def get_registered_items(self, producer=None):
        """Returns a queryset of dispatched DispatchItemRegister model
        instances for this dispatch_container_register or producer."""
        if producer:
            return DispatchItemRegister.objects.using(self.get_using_source()).filter(
                producer=self.get_producer(),
                is_dispatched=True,
                return_datetime__isnull=True)
        else:
            return DispatchItemRegister.objects.using(self.get_using_source()).filter(
                dispatch_container_register=self.get_container_register_instance(),
                is_dispatched=True,
                return_datetime__isnull=True)

    def _register_item(self, instance, user_container=None):
        """Creates an instance of DispatchItemRegister for an user
        model instance being dispatched.

        ...note: If an instance of dispatch item register already
                 exists it will be reused (get_or_create)"""
        dispatch_item_register = None
        if instance._meta.app_label not in settings.DISPATCH_APP_LABELS and not instance.include_for_dispatch():
            raise ImproperlyConfigured('Model {0} is not configured for dispatch. See model '
                                       'method \'include_for_dispatch\'  or settings attribute '
                                       'DISPATCH_APP_LABELS.'.format(instance._meta.object_name))

        if (instance.is_dispatched_as_item(user_container=user_container) and
                not self.in_session_container(instance, 'dispatched')):
            raise AlreadyDispatched('Model {0} instance {1} is already dispatched.'.format(
                instance._meta.object_name, instance))
        if self.in_session_container(instance, 'dispatched'):
            dispatch_item_register = True
        else:
            try:
                dispatch_item_register = DispatchItemRegister.objects.using(self.get_using_source()).get(
                    dispatch_container_register=self.get_container_register_instance(),
                    item_identifier=getattr(instance, self.get_user_item_identifier_attrname()),
                    item_pk=instance.pk)
                dispatch_item_register.is_dispatched = True
                dispatch_item_register.return_datetime = None
                dispatch_item_register.producer = self.get_producer()
                dispatch_item_register.dispatch_host = socket.gethostname()
                dispatch_item_register.dispatch_using = self.get_producer().settings_key
                dispatch_item_register.item_app_label = instance._meta.app_label
                dispatch_item_register.item_model_name = instance._meta.object_name  # not lower!
                dispatch_item_register.item_identifier_attrname = self.get_user_item_identifier_attrname()
                dispatch_item_register.save()
            except DispatchItemRegister.DoesNotExist:
                dispatch_item_register = DispatchItemRegister.objects.using(self.get_using_source()).create(
                    dispatch_container_register=self.get_container_register_instance(),
                    item_identifier=getattr(instance, self.get_user_item_identifier_attrname()),
                    item_pk=instance.pk,
                    is_dispatched=True,
                    return_datetime=None,
                    producer=self.get_producer(),
                    dispatch_host=socket.gethostname(),
                    dispatch_using=self.get_producer().settings_key,
                    item_app_label=instance._meta.app_label,
                    item_model_name=instance._meta.object_name,  # not lower!
                    item_identifier_attrname=self.get_user_item_identifier_attrname(),
                    )
            except IntegrityError:
                raise ImproperlyConfigured('Attempting to dispatch a model that is not \"dispatchable\". '
                                           'Expected instance.is_dispatched=True for Model{0}. Please '
                                           'check that this model has method \'include_for_dispatch()\' '
                                           'or model\'s app_label is included in settings.'
                                           'DISPATCH_APP_LABELS'.format(instance._meta.object_name))
            self.add_to_session_container(instance, 'dispatched')
        return dispatch_item_register

    def get_membershipform_models(self):
        """Returns a list of 'visible' membership form model classes."""
        return [membership_form.content_type_map.content_type.model_class()
                for membership_form in MembershipForm.objects.using(
                    self.get_using_source()).filter(visible=True)]

    def set_visit_model_cls(self, app_label, model_cls):
        """Sets the visit_model_cls attribute with a dictionary of tuples (field name, class) by app.
        """
        from edc.subject.visit_tracking.models import BaseVisitTracking
        self._visit_models = {}
        if not model_cls:
            raise TypeError('Parameter model_cls cannot be None.')
        for field in model_cls._meta.fields:
            if isinstance(field, (ForeignKey, OneToOneField)):
                field_cls = field.rel.to
                if issubclass(field_cls, BaseVisitTracking):
                    # does this dict ever have more than one entry??
                    self._visit_models.update({app_label: (field.name, field_cls)})

    def get_visit_model_cls(self, app_label, model_cls=None, **kwargs):
        """Returns a tuple of (field name, class) or just one of
        the tuple items.

        Keywords:
            index: either 'name' or 'cls'. If specified, only returns
                   the item in the tuple instead of the whole tuple.
        """
        if not self._visit_models.get(app_label):
            self.set_visit_model_cls(app_label, model_cls)
        # check for kwarg 'key' and set key to 0 or 1 (or None if not found)
        index = {'name': 0, 'cls': 1}.get(kwargs.get('index', None), None)
        if not self._visit_models.get(app_label):
            tpl = (None, None)
        else:
            tpl = self._visit_models.get(app_label)
        if index in [0, 1]:
            return tpl[index]
        else:
            return tpl
