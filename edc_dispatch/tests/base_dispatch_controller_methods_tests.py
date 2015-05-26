from django.db import IntegrityError
from django.db.models import get_model
from django.test import TestCase

from edc.device.sync.exceptions import ProducerError
from edc.device.sync.models import Producer
from edc.testing.tests.factories import TestDspContainerFactory, TestDspContainer

from ..classes import BaseDispatch, ReturnController, BaseDispatchController
from ..exceptions import AlreadyDispatchedContainer, AlreadyRegisteredController
from ..models import DispatchContainerRegister, DispatchItemRegister


class BaseDispatchControllerMethodsTests(TestCase):

    def setUp(self, user_container_app_label=None, user_container_model_name=None, user_container_identifier_attrname=None, user_container_identifier=None, dispatch_item_app_label=None):
        Producer.objects.create(name='test_producer', settings_key='dispatch_destination', is_active=True)
        self.producer = None
        self.outgoing_transaction = None
        self.incoming_transaction = None
        self.using_source = 'default'
        self.using_destination = 'dispatch_destination'
        self.user_container_app_label = user_container_app_label or 'bhp_base_test'
        self.user_container_model_name = user_container_model_name or 'testdispatchcontainer'
        self.user_container_identifier_attrname = user_container_identifier_attrname or 'test_container_identifier'
        self.user_container_identifier = user_container_identifier or 'TEST_IDENTIFIER'
        self.dispatch_item_app_label = 'bhp_base_test'  # usually something like 'mochudi_subject'
        # create an instance for the container before initiation the class
        self.create_test_container()

    def create_test_container(self):
        self.test_container = TestDspContainer.objects.create(test_container_identifier=self.user_container_identifier)

#     def test_container_p1(self):
#         """Tests for exception if attempting to use a container as an item."""
#         self.base_controller = None
#         # assert that you cannot use TestItem as a container model
#         self.assertRaises(DispatchError, BaseDispatch,
#             'default',
#             'dispatch_destination',
#             self.user_container_app_label,
#             'testitem',
#             'id',
#             '0')

    def test_container_p2(self):
        test_container = TestDspContainerFactory()
        base_controller = BaseDispatch(
            'default',
            'dispatch_destination',
            test_container._meta.app_label,
            test_container._meta.object_name,
            'test_container_identifier',
            test_container.test_container_identifier)
        #assert a dispatch container instance exists
        self.assertIsInstance(base_controller.get_container_register_instance(), DispatchContainerRegister)
        # assert there is only one
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 1)
        # get dispatch_container_register
        dispatch_container_register = base_controller.get_container_register_instance()
        # assert that dispatch container instance producer is correct
        self.assertEqual(dispatch_container_register.producer, base_controller.get_producer())
        # assert dispatch container instance is_dispatched=True
        self.assertTrue(dispatch_container_register.is_dispatched)
        # assert values used to register user_container in dispatch_container_register_instance
        self.assertEquals(dispatch_container_register.container_identifier, base_controller.get_user_container_identifier())
        # get the user container instance, e.g. Household
        obj_cls = get_model(
            base_controller.get_container_register_instance().container_app_label,
            base_controller.get_container_register_instance().container_model_name)
        # assert this is TestContainer
        self.assertTrue(issubclass(obj_cls, TestDspContainer))
        # assert this is TestContainer instance
        self.assertIsInstance(
            obj_cls.objects.get(**{dispatch_container_register.container_identifier_attrname: dispatch_container_register.container_identifier}),
            obj_cls)
        obj = obj_cls.objects.get(**{dispatch_container_register.container_identifier_attrname: dispatch_container_register.container_identifier})
        # assert the user container identifier value in the DispatchContainerRegister is the same as is returned by get_user_container_identifier
        self.assertEquals(dispatch_container_register.container_identifier, base_controller.get_user_container_identifier())
        #assert get user container instance using base_controller methods
        obj2 = obj_cls.objects.get(**{base_controller.get_user_container_identifier_attrname(): base_controller.get_container_register_instance().container_identifier})
        self.assertEqual(obj2.pk, obj.pk)
        # assert that user container model method returns identifier attrname that is same as one used to init the class
        self.assertEqual(obj.dispatched_as_container_identifier_attr(), base_controller.get_user_container_identifier_attrname())
        # assert is an instance of TestContainer
        self.assertTrue(isinstance(obj, TestDspContainer))
        # assert is a dispatchable model
        self.assertTrue(obj.is_dispatchable_model())
        # assert that user container model is flagged as a container model
        self.assertTrue(obj.is_dispatch_container_model())
        # assert that users container model is flagged as dispatched as a container (DispatchContainer)
        self.assertTrue(obj.is_dispatched_as_container())
        # assert that users container model is NOT flagged as dispatched as an item (DipatchItem)
        self.assertFalse(obj.is_dispatched_as_item())
        # assert that user container instance is dispatched
        #self.assertTrue(obj.is_dispatched())
        # assert that DispatchContainer exists for this user container model
        self.assertIsInstance(DispatchContainerRegister.objects.get(container_identifier=getattr(obj, dispatch_container_register.container_identifier_attrname)), DispatchContainerRegister)
        # assert that DispatchContainer for this user container model is flagged as is_dispatched
        self.assertTrue(DispatchContainerRegister.objects.get(container_identifier=getattr(obj, dispatch_container_register.container_identifier_attrname)).is_dispatched)
        # assert that DispatchContainer for this user container model return_datetime is not set
        self.assertIsNone(DispatchContainerRegister.objects.get(container_identifier=getattr(obj, dispatch_container_register.container_identifier_attrname)).return_datetime)
        # assert model cannot be saved on default
        self.assertRaises(AlreadyDispatchedContainer, obj.save)
        #print [o for o in DispatchItemRegister.objects.all()]
        #print [o for o in DispatchContainerRegister.objects.all()]

    def test_dispatch_p1(self):
        """Tests dispatch and return on a Container."""
        DispatchContainerRegister.objects.all().delete()
        base_controller = BaseDispatchController(
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # get dispatch_container_register
        dispatch_container_register = base_controller.get_container_register_instance()
        # get the user container instance, e.g. Household
        user_container_cls = get_model(
            base_controller.get_container_register_instance().container_app_label,
            base_controller.get_container_register_instance().container_model_name)
        # assert this is TestContainer
        self.assertTrue(issubclass(user_container_cls, TestDspContainer))
        # assert this is TestContainer instance
        self.assertIsInstance(
            user_container_cls.objects.get(**{dispatch_container_register.container_identifier_attrname: dispatch_container_register.container_identifier}),
            user_container_cls)
        user_container = user_container_cls.objects.get(**{dispatch_container_register.container_identifier_attrname: dispatch_container_register.container_identifier})
        #dispatch as json
        base_controller.dispatch_user_container_as_json(user_container)
        self.assertEqual(DispatchItemRegister.objects.all().count(), 1)
        self.assertEquals(DispatchItemRegister.objects.using(self.using_source).filter(dispatch_container_register=dispatch_container_register).count(), 1)
        # update the dispatch_container_register instance as returned
        return_controller = ReturnController(self.using_source, self.using_destination)
        return_controller.return_dispatched_items(user_container)
        # assert that model method also indicates that the instance is NOT dispatched
        self.assertFalse(user_container.is_dispatched_as_container())
        self.assertFalse(user_container.is_dispatched_as_item())
        # assert the model saves without an exception
        self.assertIsNone(user_container.save())
        DispatchContainerRegister.objects.all().delete()

    def test_producer_p1(self):
        """Tests that you cannot change the producer after the controller is instantiated."""
        Producer.objects.all().delete()
        producer = Producer.objects.create(name='test_producer', settings_key='dispatch_destination', is_active=True)
        # assert there is a contraint on settings_key and is_active
        self.assertRaises(IntegrityError, Producer.objects.create, name='test_producer', settings_key='dispatch_destination', is_active=True)
        base_controller = BaseDispatchController(
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # assert the correct producer is returned
        self.assertEqual(producer.settings_key, base_controller.get_producer().settings_key)
        # assert it is an active producer
        self.assertTrue(base_controller.get_producer().is_active)
        producer.is_active = False
        producer.save()
        # assert you cannot change the producer once set
        self.assertRaises(ProducerError, base_controller.set_producer)
        base_controller = None
        # create a new base_controller knowing there are NO active producers
        self.assertRaises(ProducerError, BaseDispatchController,
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # create new active producer but not for this settings_key
        Producer.objects.create(name='test_producer_2', settings_key='default', is_active=True)
        # create a new base_controller knowing there are NO active producers for this settings_key
        self.assertRaises(ProducerError, BaseDispatchController,
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)

    def test_producer_p2(self):
        """Tries to create a new Controller without a producer, set the producer, change it, etc"""
        Producer.objects.all().delete()
        # assert raises ProducerError becuase there is no producer
        self.assertRaises(ProducerError, BaseDispatchController,
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # create a producer, but not active
        Producer.objects.create(name='test_producer1', settings_key='dispatch_destination', is_active=False)
        # assert raises ProducerError becuase there is no producer
        self.assertRaises(ProducerError, BaseDispatchController,
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # create a producer, but not with this settings key
        Producer.objects.create(name='test_producer2', settings_key='default', is_active=True)
        # assert raises ProducerError becuase there is no producer
        self.assertRaises(ProducerError, BaseDispatchController,
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        producer = Producer.objects.get(name='test_producer1', settings_key='dispatch_destination')
        producer.is_active = True
        producer.save()
        # create a controller
        base_controller = BaseDispatchController(
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # assert the correct producer was selected
        self.assertEqual('test_producer1', base_controller.get_producer().name)
        # assert that producer, once set, cannot be changed
        self.assertRaises(ProducerError, base_controller.set_producer)

    def test_producer_p3(self):
        """Tests the dispatch_controller_register which does not allow two instances of BaseDispatchController to exist for the same settings_key."""
        Producer.objects.all().delete()
        Producer.objects.create(name='test_producer1', settings_key='dispatch_destination', is_active=True)
        Producer.objects.create(name='test_producer2', settings_key='survey', is_active=True)
        # create a controller
        base_controller = BaseDispatchController(
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        base_controller2 = BaseDispatchController(
            'default',
            'survey',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # create again, assert raises AlreadyRegistered
        self.assertRaises(AlreadyRegisteredController, BaseDispatchController,
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # create again, assert raises AlreadyRegistered
        self.assertRaises(AlreadyRegisteredController, BaseDispatchController,
            'default',
            'survey',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # destroy base_controller2
        del base_controller2
        #create a controller with a new variable
        base_controller3 = BaseDispatchController(
            'default',
            'survey',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
#        print registered_dispatch_controllers._register
        # create a controller reusing base_controller variable
        base_controller = BaseDispatchController(
            'default',
            'dispatch_destination',
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
