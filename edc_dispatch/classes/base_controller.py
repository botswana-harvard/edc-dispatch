import logging
import socket

from datetime import datetime

from django.conf import settings
from django.core import serializers
from django.core.exceptions import ImproperlyConfigured
from django.core.serializers.base import DeserializationError
from django.db import IntegrityError
from django.db.models import ForeignKey, OneToOneField
from django.db.models import Q, Count, Max
from django.apps import apps
from django.db.models.query import QuerySet
from django_crypto_fields.classes import FieldCryptor
from django_crypto_fields.fields import BaseEncryptedField
from django_crypto_fields.models import Crypt

from lis.base.model.models import BaseLabListModel, BaseLabListUuidModel

from edc.base.model.models import BaseListModel
from edc.core.bhp_variables.models import StudySite
from edc_sync.classes import BaseProducer
from edc_sync.exceptions import PendingTransactionError
from edc_sync.helpers import TransactionHelper
from edc_entry.models import BaseEntryMetaData
from edc_subject.visit_schedule.models import VisitDefinition, ScheduleGroup

from ..exceptions import ControllerBaseModelError

from .controller_register import registered_controllers


logger = logging.getLogger(__name__)


class NullHandler(logging.Handler):
    def emit(self, record):
        pass
nullhandler = logger.addHandler(NullHandler())


class BaseController(BaseProducer):

    APP_NAME = 0
    MODEL_NAME = 1

    def __repr__(self):
        return self._repr()

    __str__ = __repr__

    def __del__(self):
        """Deregisters for this producer.settings_key."""
        registered_controllers.deregister(self)

    def _repr(self):
        return '{0}for {1}'.format('BaseController', self.get_producer().settings_key)

    def __init__(self, using_source, using_destination, **kwargs):
        """Initializes and verifies arguments ``using_source`` and ``using_destination``.

        Args:
            ``using_source``: settings.DATABASE key for source. Source is the server so must
                          be 'default' if running on the server and 'server'
                          if running on the device.
            ``using_destination``: settings.DATABASE key for destination. If running from the server
                               this key must exist in settings.DATABASES. If on the device, must be 'default'.
                               In either case, ``using_destination`` must be found in the
                               source :class:`Producer` model as producer.settings_key (see :func:`set_producer`.)

        Keywords:
            ``server_device_id``: settings.DEVICE_ID for server (default='99')

        Settings:
            DISPATCH_APP_LABELS = a list of app_labels for apps that contain models
                to be monitored by dispatch. Models in apps not
                here will be ignored by default. To ignore a model that
                exists in an app listed here, override the
                :func:`ignore_for_dispatch` method on the model. See
                model base class :class:`BaseSyncUuidModel` in
                module :mod:`bhp_sync`.
                For example:
                    DISPATCH_APP_LABELS = ['mochudi_household', 'mochudi_subject', 'mochudi_lab']
            """
        self._controller_state = None
        self._model_pk_container = {}
        self._session_container = {}
        # self.signal_manager = SignalManager()
        self.initialize_session_container()
        super(BaseController, self).__init__(using_source, using_destination, **kwargs)
        self.fk_instances = []
        self.preparing_status = kwargs.get('preparing_netbook', None)
        if 'DISPATCH_APP_LABELS' not in dir(settings):
            raise ImproperlyConfigured('Attribute DISPATCH_APP_LABELS not found. '
                                       'Add to settings. e.g. DISPATCH_APP_LABELS '
                                       '= [\'mochudi_household\', \'mochudi_subject\', '
                                       '\'mochudi_lab\']')
        self.set_producer()
        return None

    def set_controller_state(self, value):
        self._controller_state = value
        if self._controller_state == 'retry':
            # preload session_container dispatched items
            self.preload_session_container()

    def get_controller_state(self):
        if not self._controller_state:
            self.set_controller_state('ready')
        return self._controller_state

    def has_pending_transactions(self, models):
        return self.has_incoming_transactions(models) or self.has_outgoing_transactions()

    def has_outgoing_transactions(self):
        """Check if destination has pending Outgoing Transactions by checking is_consumed in
           bhp_sync.outgoing_transactions.
        """
        return TransactionHelper().has_outgoing(self.get_using_destination())

    def has_outgoing_transactions_producer(self):
        """Check if destination has pending Outgoing Transactions by checking is_consumed in
           bhp_sync.outgoing_transactions.
        """
        producer_hostname = self.get_using_destination().split('-')[0]
        return TransactionHelper().has_outgoing_for_producer(producer_hostname,
                                                             self.get_using_destination())

    def has_incoming_transactions(self, models=None):
        """Check if source has pending Incoming Transactions for this producer and model(s).
        """
        retval = False
        if TransactionHelper().has_incoming_for_producer(self.get_producer_name(), self.get_using_source()):
            retval = True
        if not retval:
            if models:
                if isinstance(models, QuerySet):
                    models = [model for model in models]
                if not isinstance(models, list):
                    models = [models]
                if TransactionHelper().has_incoming_for_model(
                        [model._meta.object_name for model in models], self.get_using_source()):
                    retval = True
        return retval

    def get_recent(self, model_cls, destination_hostname=None):
        """Returns a queryset of the most recent instances from the model for all but the current host."""
        source_instances = model_cls.objects.none()
        if not destination_hostname:
            destination_hostname = socket.gethostname()
        options = self.get_last_modified_options(model_cls)
        if options:
            qset = Q()
            for dct in options:
                qset.add(Q(**dct), Q.OR)
            source_instances = model_cls.objects.using(self.get_using_source()).filter(qset).order_by('id')
        else:
            source_instances = model_cls.objects.using(self.get_using_source()).all().order_by('id')
        return source_instances

    def get_last_modified_options(self, model_cls):
        """Returns a dictionary of {'hostname_modified': '<hostname>', 'modified__max': <date>, ... }."""
        options = []
        # get hostnames from source and populate default dictionary
        if 'hostname_modified' in [field.name for field in model_cls._meta.fields]:
            hostnames = model_cls.objects.using(self.get_using_source()).values(
                'hostname_modified').annotate(Count('hostname_modified')).order_by()
            for item in hostnames:
                options.append({'hostname_modified': item.get('hostname_modified'),
                                'modified__gt': datetime(1900, 1, 1)})
            valuesset = model_cls.objects.using(self.get_using_destination()).values(
                'hostname_modified').all().annotate(Max('modified')).order_by()
            for item in valuesset:
                for n, dct in enumerate(options):
                    if dct.get('hostname_modified') == item.get('hostname_modified'):
                        dct.update({'hostname_modified': item.get('hostname_modified'),
                                    'modified__gt': item.get('modified__max')})
                        options[n] = dct
        return options

    def model_to_json(self, model_cls, additional_base_model_class=None, fk_to_skip=None):
        """Sends all instances of the model class to :func:`_to_json`."""
        self._to_json(model_cls.objects.all(), additional_base_model_class, fk_to_skip=fk_to_skip)

    def is_allowed_base_model_cls(self, cls, additional_base_model_class=None):
        """Returns True or raises an exception if the class is a subclass
        of a base model class allowed for serialization."""
        if not issubclass(cls, self._get_allowed_base_models(additional_base_model_class)):
            raise ControllerBaseModelError('For dispatch, user model \'{0}\' must '
                                           'be a subclass of \'{1}\'. Got {2}'.format(
                                               cls, self._get_allowed_base_models()))
        return True

    def is_allowed_base_model_instance(self, inst, additional_base_model_class=None):
        """Returns True or raises an exception if the class
        is an instance of a base model class allowed for serialization."""
        if not isinstance(inst, self._get_allowed_base_models(additional_base_model_class)):
            raise ControllerBaseModelError('For dispatch, user model \'{0}\' must be '
                                           'an instance of \'{1}\'. Got {2}'.format(
                                               inst._meta.object_name,
                                               self._get_allowed_base_models(), inst.__class__))
        return True

    def _get_allowed_base_models(self, additional_base_model_class=None):
        """Returns a tuple of base model classes that may be serialized to json."""
        from edc.subject.lab_tracker.models import BaseHistoryModel
        base_model_class = self.get_allowed_base_models()
        if not isinstance(base_model_class, list):
            raise TypeError('Expected list of base_model classes.')
        if additional_base_model_class:
            if not isinstance(additional_base_model_class, (list, tuple)):
                additional_base_model_class = [additional_base_model_class]
            base_model_class = base_model_class + additional_base_model_class
        base_model_class = base_model_class + [BaseListModel, BaseLabListModel,
                                               BaseLabListUuidModel, VisitDefinition,
                                               ScheduleGroup, StudySite, BaseHistoryModel,
                                               BaseEntryMetaData, BaseEncryptedField]
        return tuple(base_model_class)

    def get_allowed_base_models(self):
        """Returns a list of base model classes that may be serialized to json.

        Users may override

        This is evaluated in method :func:`_to_json` before serializing an instance. """
        return []

    def _get_base_models_for_default_serialization(self):
        """Wraps :func:`get_allowed_base_models`."""
        from edc.subject.lab_tracker.models import BaseHistoryModel
        base_model_class = self.get_base_models_for_default_serialization()
        if not isinstance(base_model_class, list):
            raise TypeError('Expected base_model classes as a list. Got{0}'.format(base_model_class))
        base_model_class = base_model_class + [BaseListModel, BaseLabListModel, BaseLabListUuidModel,
                                               VisitDefinition, StudySite, BaseHistoryModel,
                                               BaseEntryMetaData]
        return tuple(set(base_model_class))

    def get_base_models_for_default_serialization(self):
        """Returns a tuple of base models from which subclasses should use the
        default method :func:`_to_json` and not a callback from the sender.

        This is evaluated when serializing the foreign keys on an instance and
        you need to know if you can use the callback to serialize the foreign key
        or not."""
        return []

    def get_fk_dependencies(self, instances, fk_to_skip=None):
        """Updates the list of foreign key instances required for serialization of the provided instances.

            Args:
                instances: an iterable of model instances
                fk_to_skip: the field attname of a foreignkey that is assumed to be on the
                            destination device and may be skipped. To be used carefully.
        """
        if fk_to_skip:
            if not isinstance(fk_to_skip, list):
                raise TypeError('Expected a list in \'get_fk_dependencies\'')
        else:
            fk_to_skip = []
        for obj in instances:
            for field in obj._meta.fields:
                if isinstance(field, (ForeignKey, OneToOneField)) and field.attname not in fk_to_skip:
                    pk = getattr(obj, field.attname)
                    cls = field.rel.to
                    if (cls, pk) not in self.get_session_container('fk_dependencies'):
                        if cls.objects.filter(pk=pk).exists():
                            this_fk = cls.objects.get(pk=pk)
                            self.fk_instances.append(this_fk)
                            self.get_fk_dependencies([this_fk])
                        self.add_to_session_container((cls, pk), 'fk_dependencies')

    def add_to_session_container(self, instance, key):
        if instance not in self._session_container[key]:
            self._session_container[key].append(instance)

    def load_session_container_class_counter(self, app_label):
        _models = []
        if not app_label:
            raise TypeError('Parameter \'app_label\' cannot be None.')
        app = get_app(app_label)
        for model_cls in get_models(app):
            self._session_container['class_counter'].update({model_cls._meta.object_name, 0})

    def initialize_session_container(self):
        self._session_container = {'serialized': [], 'dispatched': [], 'fk_dependencies': [], 'class_counter': {}}

    def get_session_container(self, key):
        return self._session_container[key]

    def in_session_container(self, instance, key):
        if instance in self.get_session_container(key):
            return True
        return False

    def session_container_ready(self):
        for key in self._session_container:
            if self.get_session_container(key):
                return False
        return True

    def update_session_container_class_counter(self, instance):
        cnt = self._session_container['class_counter'].get(instance._meta.object_name, 0)
        self._session_container['class_counter'].update({instance._meta.object_name: cnt + 1})

    def get_session_container_class_counter_count(self, instance):
        if self._session_container['class_counter'].get(instance._meta.object_name, None) is None:
            self._session_container['class_counter'].update({instance._meta.object_name: 0})
        return self._session_container['class_counter'].get(instance._meta.object_name)

    def update_model(self, model_or_app_model_tuple, additional_base_model_class=None, fk_to_skip=None):
        try:
            app, model = model_or_app_model_tuple
            model_cls = get_model(app, model)
            if not model_cls:
                raise ValueError
        except ValueError:
            model_cls = model_or_app_model_tuple
        self.model_to_json(model_cls, additional_base_model_class, fk_to_skip=fk_to_skip)

    def update_model_crypts(self, mld_cls_instances):
        """Grabs all crypt objects of models being dispatched. """
        crypt_objs_instances = []
        crypt_objs_instance = []
        if not isinstance(mld_cls_instances, (list, QuerySet)):
            mld_cls_instances = [mld_cls_instances]
        for mld_cls_instance in mld_cls_instances:  # eg plot
            # Get model
            model_cls = mld_cls_instance.__class__
            if '_meta' not in dir(model_cls):
                continue
            fields = model_cls._meta.fields
            for f in fields:
                if issubclass(f.__class__, BaseEncryptedField):
                    crypt = FieldCryptor('rsa', 'local')
                    hash_value = crypt.get_hash(getattr(mld_cls_instance, f.name))
                    # if hash_value:
                    if Crypt.objects.filter(hash=hash_value).exists():
                        crypt_objs_instance = Crypt.objects.filter(hash=hash_value)
                    else:
                        crypt = FieldCryptor('rsa', 'restricted')
                        hash_value = crypt.get_hash(getattr(mld_cls_instance, f.name))
                        if Crypt.objects.filter(hash=hash_value).exists():
                            crypt_objs_instance = Crypt.objects.filter(hash=hash_value)
                        else:
                            crypt = FieldCryptor('aes', 'local')
                            hash_value = crypt.get_hash(getattr(mld_cls_instance, f.name))
                            if Crypt.objects.filter(hash=hash_value).exists():
                                crypt_objs_instance = Crypt.objects.filter(hash=hash_value)
                            else:
                                if hash_value:
                                    raise TypeError('Could not get a secret for field={}, of model={}, using hash={}'.format(str(f), str(model_cls), hash))
                                else:
                                    pass
                    if len(crypt_objs_instance) > 0:
                        crypt_objs_instances.append(crypt_objs_instance[0])
#                     if crypt_objs_instance:hash
#                         # Successfully pulled a crypt record using hash generated from RSA instance.
#                         crypt_objs_instances.append(crypt_objs_instance[0])
#                     elif not crypt_objs_instance:
#                         crypt = FieldCryptor('rsa', 'restricted')
#                         hash_value = crypt.get_hash(getattr(mld_cls_instance, f.name))
#                         #if hash_value:
#                         crypt_objs_instance = Crypt.objects.filter(hash=hash_value)
#                         crypt_objs_instances.append(crypt_objs_instance[0])
#                     else:
#                         # RSA hash dis not work, now we try AES generated hash
#                         crypt = FieldCryptor('aes', 'local')
#                         hash_value = crypt.get_hash(getattr(mld_cls_instance, f.name))
#                         if hash_value:
#                             crypt_objs_instance = Crypt.objects.filter(hash=hash_value)
#                             if crypt_objs_instance:
#                                     crypt_objs_instances.append(crypt_objs_instance[0])
        crypt_objs_instances_unique = {}
        for crypt in crypt_objs_instances:
            crypt_objs_instances_unique[crypt.hash] = crypt
        crypt_objs_instances = crypt_objs_instances_unique.values()
        return crypt_objs_instances

    def _to_json(self, model_instance, additional_base_model_class=None, user_container=None, fk_to_skip=None):
        """Serialize model instances on source to destination.

        Args:
            model_instances: a model instance, list of model instances, or QuerySet
            additional_base_model_class: add a single or list of additional
            Base classes that the model instances inherit from. use sparingly.

        ..warning:: This method assumes you have confirmed that the
                    model_instances are "already dispatched" or not.

        """
        # Get all Crypts for this list of instances
        crypts_dispatched = self.update_model_crypts(model_instance)
        # convert to list if not iterable
        if not isinstance(model_instance, (list, QuerySet)):
            model_instance = [model_instance]
        if isinstance(model_instance, QuerySet):
            model_instance = [m for m in model_instance]
        # append crypts to all instances to be dispatched
        model_instances = crypts_dispatched + model_instance
        if self.has_incoming_transactions(model_instances):
            raise PendingTransactionError('One or more listed models have pending incoming '
                                          'transactions on \'{0}\'. Consume them first. Got '
                                          '\'{1}\'.'.format(self.get_using_source(),
                                                            list(set(model_instances))))
        if model_instances:
            for instance in model_instances:
                # confirm all model_instances are of the correct base class
                if self.is_allowed_base_model_instance(instance, additional_base_model_class):
                    # only need to check one as all are of the same class so jump out...
                    break
            self.fk_instances = []  # clear from previous
            while True:
                # add foreign key instances to the list of model instances to serialize
                self.get_fk_dependencies(model_instances, fk_to_skip)
                break
            model_instances = self.fk_instances + model_instances
            if model_instances:
                # serialize all
                json_obj = serializers.serialize('json', model_instances,
                                                 ensure_ascii=False, use_natural_keys=True, indent=2)
                # deserialize all
                deserialized_objects = []
                try:
                    deserialized_objects = serializers.deserialize("json", json_obj, use_natural_keys=True, using=self.get_using_destination())
                except DeserializationError as e:
                    if 'Appointment matching query does not exist' in str(e):
                        pass
                    else:
                        raise
                # deserialized_objects = list(deserialized_objects)
                saved = []
                tries = 0
                while True:
                    tries += 1
                    deserialized_count = 0
                    for deserialized_object in deserialized_objects:
                        deserialized_count = deserialized_count + 1
                        try:
                            if deserialized_object not in saved:
                                # save deserialized_object to destination
                                deserialized_object.save(using=self.get_using_destination())
                                self.serialize_m2m(deserialized_object)
                                saved.append(deserialized_object)
                                self.add_to_session_container(instance, 'serialized')
                                self.update_session_container_class_counter(instance)
                        except IntegrityError as integrity_error:
                            # raise IntegrityError('{}. Got {}.'.format(deserialized_object, str(integrity_error)))
                            if integrity_error.args[1].find('Duplicate entry'):
                                saved.append(deserialized_object)
                            #  TODO: change the handling of the exception to something like this:
                            #         as is raises IndexError: tuple index out of range
#                             if 'Duplicate entry' in str(integrity_error):  # and 'hash' not in str(integrity_error):
#                                 saved.append(deserialized_object)
#                             elif 'columns hash, algorithm, mode are not unique' in str(integrity_error):
#                                 # don't worry about duplicate Crypts?
#                                 saved.append(deserialized_object)
#                             else:
#                                 # only include this if you are OK passing ALL integrity errors
#                                 saved.append(deserialized_object)
                            continue
                    if len(saved) == deserialized_count:
                        break
                    if tries > 20:
                        raise DeserializationError('Unable to deserialize object. Tries exceeded '
                                                   'on {0}. Got {1}'.format(
                                                       deserialized_object.object.__class__,
                                                       str(integrity_error)))

    def serialize_dependencies(self, d_obj, user_container, to_json_callback):
        """Checks for foreign keys and, if found, sends using the callback.

        Ensures the sent instance is complete / stable

        TODO: any issue about natural keys?? this searched the destination on pk."""
        self.serialize_m2m(d_obj, user_container, to_json_callback)

    def serialize_m2m(self, d_obj):
        """Checks for M2M.

        If found, populate the list table, then add the list items to the m2m field.
        See https://docs.djangoproject.com/en/dev/topics/db/examples/many_to_many/"""
        for m2m_rel_mgr in d_obj.object._meta.many_to_many:
            pk = getattr(d_obj.object, 'pk')
            # get class of this model
            cls = d_obj.object.__class__
            # get instance of this model on source
            inst = cls.objects.get(pk=pk)
            # get the name of the m2m attribute. Note, this is not a model field but a manager
            m2m = m2m_rel_mgr.name
            # try something like test_item_m2m.m2m.all(), gets all() list_model instances for this m2m
            m2m_qs = getattr(inst, m2m).all()
            # create list_model instances on destination if they do not exist
            # dst_list_item_natural_keys = []  # list of tuples returned by natural key on list item
            dst_list_item_pks = []
            for src_list_item in m2m_qs:
                if not src_list_item.__class__.objects.using(
                        self.get_using_destination()).filter(pk=src_list_item.pk).exists():
                    # no need to use callback, list models are not registered with dispatch
                    self._to_json(src_list_item, additional_base_model_class=BaseListModel)
                    # record source pk for use later
                # dst_list_item_natural_keys.append(src_list_item.natural_key())
                dst_list_item_pks.append(src_list_item.pk)
            # get instance of this model on destination
            dest_inst = cls.objects.using(self.get_using_destination()).get(pk=pk)
            # find the pk for each list model instance and add to the m2m "field"
            # for values_tpl in dst_list_item_natural_keys:
            for pk in dst_list_item_pks:
                # get the list_model instance on destination
                item_inst = src_list_item.__class__.objects.using(self.get_using_destination()).get(pk=pk)
                # add to m2m rel_manager on destination, this is like instance.m2m.add(item)
                getattr(dest_inst, m2m).add(item_inst)  # calls the signal
