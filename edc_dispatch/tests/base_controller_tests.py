from django.test import TestCase

from edc.device.sync.models import Producer, OutgoingTransaction, IncomingTransaction
from edc.device.sync.tests.factories import ProducerFactory
from edc.testing.models import TestDspItem, TestDspContainer, TestDspItemBypass
from edc.testing.tests.factories import TestDspItemFactory, TestDspContainerFactory, TestDspItemBypassFactory
from edc.testing.tests.factories import TestM2mFactory

from ..classes import BaseDispatchController, DispatchController, ReturnController
from ..exceptions import AlreadyDispatchedContainer, AlreadyDispatchedItem
from ..models import DispatchItemRegister, DispatchContainerRegister


class BaseControllerTests(TestCase):

    def setUp(self):
        self.base_dispatch_controller = None
        self.producer = None
        self.test_container = None
        self.outgoing_transaction = None
        self.incoming_transaction = None
        self.using_source = 'default'
        self.using_destination = 'dispatch_destination'
        self.user_container_app_label = 'dispatch'
        self.user_container_model_name = 'testcontainer'
        self.user_container_identifier_attrname = 'test_container_identifier'
        self.user_container_identifier = 'TEST_IDENTIFIER'
        self.dispatch_item_app_label = 'dispatch'  # usually something like 'mochudi_subject'
        DispatchContainerRegister.objects.all().delete()
        DispatchItemRegister.objects.all().delete()

    def test_p1(self):

        class TestController(DispatchController):
            pass
            #def dispatch_prep(self):
            ##    self.dispatch_user_container_as_json(None)
            #    self.dispatch_user_items_as_json(TestItem.objects.all())

        producer = ProducerFactory(name=self.using_destination, settings_key=self.using_destination)
        l1 = TestM2mFactory()
        l2 = TestM2mFactory()
        l3 = TestM2mFactory()
        l4 = TestM2mFactory()
        l5 = TestM2mFactory()
        l6 = TestM2mFactory()
        l7 = TestM2mFactory()
        l8 = TestM2mFactory()
        l9 = TestM2mFactory()
        test_container = TestDspContainerFactory()
        t1 = TestDspItemFactory(test_container=test_container)
        t2 = TestDspItemFactory(test_container=test_container)
        t3 = TestDspItemFactory(test_container=test_container)
        t1.test_many_to_many.add(l1)
        t1.test_many_to_many.add(l2)
        t2.test_many_to_many.add(l3)
        t2.test_many_to_many.add(l4)
        t3.test_many_to_many.add(l5)
        t3.test_many_to_many.add(l6)
        t3.test_many_to_many.add(l7)
        t3.test_many_to_many.add(l8)
        t3.test_many_to_many.add(l9)
        t3.test_many_to_many.add(l1)
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 0)
        dispatch_controller = TestController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            'testcontainer',
            'test_container_identifier',
            test_container.test_container_identifier, 'http://')
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 0)
        self.assertEqual(len(dispatch_controller.get_session_container('dispatched')), 0)
        self.assertEqual(DispatchItemRegister.objects.filter(item_model_name='TestContainer').count(), 0)
        dispatch_controller.dispatch()
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 1)
        for test_item in TestDspItem.objects.using(self.using_destination).all():
            print test_item
            self.assertGreater(test_item.test_many_to_many.all().count(), 0)
            print test_item.test_many_to_many.all()

    def test_p2(self):

        class TestController(DispatchController):

            def dispatch_prep(self):
                self.dispatch_user_items_as_json(TestDspItem.objects.all())

        DispatchContainerRegister.objects.all().delete()
        DispatchItemRegister.objects.all().delete()

        producer = ProducerFactory(name=self.using_destination, settings_key=self.using_destination)
        test_container = TestDspContainerFactory()
        TestDspItemFactory(test_container=test_container)
        TestDspItemFactory(test_container=test_container)
        TestDspItemFactory(test_container=test_container)
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 0)
        dispatch_controller = TestController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            'testdispatchcontainer',
            'test_container_identifier',
            test_container.test_container_identifier, 'http://')
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 0)
        self.assertEqual(len(dispatch_controller.get_session_container('dispatched')), 0)
        self.assertEqual(DispatchItemRegister.objects.filter(item_model_name='TestContainer').count(), 0)
        dispatch_controller.dispatch()
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 1)
        self.assertEqual(DispatchItemRegister.objects.filter(item_model_name='TestContainer').count(), 1)
        self.assertEqual(TestDspItem.objects.using(self.using_destination).all().count(), 3)
        self.assertEqual(DispatchItemRegister.objects.all().count(), 4)
        self.assertEqual(dispatch_controller.get_session_container_class_counter_count(TestDspItem), 4)

        TestDspItemFactory(test_container=test_container)
        TestDspItemFactory(test_container=test_container)

#         # reload controller
#         self.assertRaises(AlreadyRegisteredController, TestController,
#             self.using_source,
#             self.using_destination,
#             self.user_container_app_label,
#             'testcontainer',
#             'test_container_identifier',
#             test_container.test_container_identifier, 'http://')
        dispatch_controller = TestController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            'testdispatchcontainer',
            'test_container_identifier',
            test_container.test_container_identifier, 'http://', retry=True)
        self.assertEqual(len(dispatch_controller.get_session_container('dispatched')), 4)
        self.assertEqual(len(dispatch_controller.get_session_container('serialized')), 4)
        #print dispatch_controller.get_session_container('dispatched')
        #print dispatch_controller.get_session_container('serialized')
        dispatch_controller.dispatch()
        # assert counts on session container
        self.assertEqual(dispatch_controller.get_session_container_class_counter_count(TestDspItem), 0)

    def test_p3(self):
        """Test P3."""
        class TestController(DispatchController):

            def dispatch_prep(self):
                self.dispatch_user_items_as_json(TestDspItem.objects.all())
        print "TEST P3"
        print "clear all tables"
        DispatchContainerRegister.objects.all().delete()
        DispatchItemRegister.objects.all().delete()
        print "create new container and items"
        producer = ProducerFactory(name=self.using_destination, settings_key=self.using_destination)
        test_container = TestDspContainerFactory()
        print "create 3 items for this container"
        TestDspItemFactory(test_container=test_container)
        TestDspItemFactory(test_container=test_container)
        TestDspItemFactory(test_container=test_container)
        print "assert nothing in DispatchContainerRegister"
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 0)
        print "instantiate a new dispatch controller with container {0}".format(test_container)
        dispatch_controller = TestController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            'testcontainer',
            'test_container_identifier',
            test_container.test_container_identifier, 'http://')
        print "assert nothing is in session container, yet ..."
        self.assertEqual(len(dispatch_controller.get_session_container('dispatched')), 0)
        self.assertEqual(len(dispatch_controller.get_session_container('serialized')), 0)
        print "call dispatch"
        dispatch_controller.dispatch(debug=True)
        print "assert 1 item in container register"
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 1)
        print "assert 4 item in item register (3 items, 1 container)"
        self.assertEquals(DispatchItemRegister.objects.all().count(), 4)
        print "try to save test container, raise an AlreadyDispatchedContainer"
        self.assertRaises(AlreadyDispatchedContainer, test_container.save)
        print "create 2 more items for this container"
        TestDspItemFactory(test_container=test_container)
        TestDspItemFactory(test_container=test_container)
        print "try to call dispatch again, raises AlreadyDispatchedContainer. Can only call dispatch once."
        self.assertRaises(AlreadyDispatchedContainer, dispatch_controller.dispatch, debug=True)
        print "instantiate a new dispatch controller with the same dispatched container"
        dispatch_controller = TestController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            'testcontainer',
            'test_container_identifier',
            test_container.test_container_identifier, 'http://')
        print "call dispatch, still raises AlreadyDispatchedContainer if debug=True"
        self.assertRaises(dispatch_controller.dispatch, debug=True)
        print "try to save test container, raise an AlreadyDispatchedContainer"
        self.assertRaises(AlreadyDispatchedContainer, test_container.save)
        print "requery test container"
        test_container = TestDspContainer.objects.get(test_container_identifier=test_container.test_container_identifier)
        print "confirm container is dispatched_as_container"
        self.assertTrue(test_container.is_dispatched_as_container())
        self.assertEqual(DispatchContainerRegister.objects.filter(is_dispatched=True).count(), 1)
        print "instantiate a return controller"
        return_controller = ReturnController(
            self.using_source,
            self.using_destination)
        print "return all items"
        return_controller.return_dispatched_items()
        print "requery container"
        test_container = TestDspContainer.objects.get(test_container_identifier=test_container.test_container_identifier)
        print "confirm container is not dispatched_as_container"
        self.assertFalse(test_container.is_dispatched_as_container())
        self.assertEqual(DispatchContainerRegister.objects.filter(is_dispatched=True).count(), 0)
        print "instantiate a new dispatch controller with the same container"
        dispatch_controller = TestController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            'testcontainer',
            'test_container_identifier',
            test_container.test_container_identifier, 'http://')
        print "call dispatch"
        dispatch_controller.dispatch(debug=True)
        print "assert still just one container registered"
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 1)
        print "assert 6 items in item register (5 items, 1 container)"
        self.assertEquals(DispatchItemRegister.objects.all().count(), 6)
        print "try to save test container, raise an AlreadyDispatchedContainer"
        self.assertRaises(AlreadyDispatchedContainer, test_container.save)

    def test_p4(self):
        """Test P4. test bypass_for_edit_dispatched_as_item"""
        class TestController(DispatchController):

            def dispatch_prep(self):
                self.dispatch_user_items_as_json(TestDspItemBypass.objects.all())

        print "TEST P4"
        print "clear all tables"
        DispatchContainerRegister.objects.all().delete()
        DispatchItemRegister.objects.all().delete()
        print "create new container and items"
        producer = ProducerFactory(name=self.using_destination, settings_key=self.using_destination)
        test_container = TestDspContainerFactory()
        print "create 3 TestItemBypassForEdit items for this container"
        test_item1 = TestDspItemBypassFactory(test_container=test_container)
        print test_item1
        TestDspItemBypassFactory(test_container=test_container)
        TestDspItemBypassFactory(test_container=test_container)
        print "assert nothing in DispatchContainerRegister"
        self.assertEqual(DispatchContainerRegister.objects.all().count(), 0)
        print "instantiate a new dispatch controller with container {0}".format(test_container)
        dispatch_controller = TestController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            'testdispatchcontainer',
            'test_container_identifier',
            test_container.test_container_identifier, 'http://')
        print "assert nothing is in session container, yet ..."
        self.assertEqual(len(dispatch_controller.get_session_container('dispatched')), 0)
        self.assertEqual(len(dispatch_controller.get_session_container('serialized')), 0)
        print "call dispatch"
        dispatch_controller.dispatch(debug=True)
        print 'assert can edit TestItemBypassForEdit because method bypass_for_edit_dispatched_as_item() is overridden if nothing changed'
        test_item1.save()
        print 'assert can edit field f1 , f2 in TestItemBypassForEdit eventhough method bypass_for_edit_dispatched_as_item() is overridden'
        test_item1.f1 = 'erik'
        test_item1.f2 = 'erik'
        test_item1.save()
        print 'assert cannot edit field f3 , f4 in TestItemBypassForEdit eventhough method bypass_for_edit_dispatched_as_item() is overridden'
        test_item1.f3 = 'erik'
        test_item1.f4 = 'erik'
        self.assertRaises(AlreadyDispatchedItem, test_item1.save)

    def create_test_container(self):
        self.test_container = TestDspContainer.objects.create(test_container_identifier=self.user_container_identifier)

    def create_test_item(self):
        if not self.test_container:
            self.create_test_container()
        self.test_item = TestDspItem.objects.create(test_item_identifier=self.user_container_identifier, test_container=self.test_container)

    def create_producer(self, is_active=False):
        # add a in_active producer
        self.producer = Producer.objects.create(name='test_producer', settings_key=self.using_destination, is_active=is_active)

    def create_sync_transactions(self):
        # add outgoing transactions and check is properly detects pending transactions before dispatching
        self.outgoing_transaction = OutgoingTransaction.objects.using(self.using_destination).create(
            tx='tx',
            tx_pk='tx_pk',
            tx_name='test_model',
            producer=self.producer.name,
            is_consumed=False)
        # create an incoming transaction
        self.incoming_transaction = IncomingTransaction.objects.using(self.using_source).create(
            tx='tx',
            tx_pk='tx_pk',
            tx_name='test_model',
            producer=self.producer.name,
            is_consumed=False)

    def create_base_dispatch_controller(self, user_container_model_name=None):
        # create base controller instance
        if not user_container_model_name:
            user_container_model_name = self.user_container_model_name
        self.base_dispatch_controller = None
        self.base_dispatch_controller = BaseDispatchController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
