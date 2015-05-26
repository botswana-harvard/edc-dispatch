from datetime import datetime

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import get_model

from edc.core.bhp_using.exceptions import UsingError, UsingSourceError
from edc.device.sync.exceptions import PendingTransactionError, ProducerError
from edc.device.sync.models import Producer, OutgoingTransaction, IncomingTransaction
from edc.subject.registration.models import RegisteredSubject

from ..classes import BaseController, ReturnController, BaseDispatchController
from ..exceptions import (DispatchError, AlreadyDispatched, DispatchControllerNotReady,
                          DispatchItemError, AlreadyDispatchedContainer)
from ..models import TestList, TestItem, TestItemTwo, TestItemThree, TestItemM2M, DispatchItemRegister, DispatchContainerRegister, TestContainer

from .base_controller_tests import BaseControllerTests


class DispatchControllerMethodsTests(BaseControllerTests):

    def test_base_methods(self):
        # Base tests
        self.assertTrue('DEVICE_ID' in dir(settings), 'Settings attribute DEVICE_ID not found')
        # raise source and destination cannot be the same
        self.assertRaises(UsingError, BaseController, self.using_source, self.using_source)
        # source must be either server or default
        self.assertRaises(UsingSourceError, BaseController, 'not_default', self.using_source)
        # no producer for destination
        self.assertRaises(ProducerError, BaseController, self.using_source, self.using_destination)
        if not self.producer:
            self.create_producer()
        self.assertIsInstance(self.producer, Producer)
        self.assertEqual(self.producer.settings_key, self.using_destination)
        # no active producer for destination
        self.assertRaises(ProducerError, BaseController, self.using_source, self.using_destination)
        # activate producer
        self.producer.is_active = True
        self.producer.save()
        # Base instance creates OK
        base_controller = BaseController(self.using_source, self.using_destination)
        self.assertIsInstance(base_controller, BaseController)
        # confirm producer instance is as expected
        self.assertEqual(base_controller.get_producer().settings_key, self.producer.settings_key)
        # DATABASE keys check works
        self.assertRaises(ImproperlyConfigured, BaseController(self.using_source, self.using_destination).is_valid_using, 'xdefault', 'source')
        # ...
        self.assertRaises(UsingSourceError, BaseController, self.using_source, self.using_destination, server_device_id=None)
        # id source is default, must be server = 99
        self.assertRaises(UsingSourceError, BaseController, self.using_source, self.using_destination, server_device_id='22')
        #TODO: improve use of DEVICE_ID and server_device_id
        Producer.objects.all().delete()
        base_controller = None

    def test_dispatch_methods_p1(self):
        """Checks pending transactions."""
        self.base_dispatch_controller = None
        TestItemThree.objects.all().delete()
        TestItemThree.objects.using(self.using_destination).all().delete()
        TestItemTwo.objects.all().delete()
        TestItemTwo.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        OutgoingTransaction.objects.using(self.using_destination).all().delete()
        OutgoingTransaction.objects.all().delete()
        IncomingTransaction.objects.using(self.using_destination).all().delete()
        IncomingTransaction.objects.all().delete()
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        if not self.producer:
            self.create_producer(True)
        # add outgoing transactions and check is properly detects pending transactions before dispatching
        self.create_sync_transactions()
        # create a user container
        self.create_test_container()
        self.assertIsInstance(self.test_container, TestContainer)
        # create a dispatch controller
        self.base_dispatch_controller = None
        self.create_base_dispatch_controller()
        # create an instance for the user container model
        # ... try get_model with self attributes first
        self.assertTrue(issubclass(get_model(self.user_container_app_label, self.user_container_model_name), TestContainer))
        self.assertEqual(TestContainer.objects.filter(**{self.user_container_identifier_attrname: self.user_container_identifier}).count(), 1)
        self.assertEqual(getattr(TestContainer.objects.get(**{self.user_container_identifier_attrname: self.user_container_identifier}), self.user_container_identifier_attrname), self.user_container_identifier)
        # assert Trasactions created
        self.assertEquals(OutgoingTransaction.objects.using(self.using_destination).filter(is_consumed=False).count(), 1)
        # assert there ARE outgoing transactions on dispatch_destination
        self.assertTrue(self.base_dispatch_controller.has_outgoing_transactions())
        #print [o for o in OutgoingTransaction.objects.using('dispatch_destination').filter(is_consumed=False)]
        # assert there ARE incoming transactions on default
        self.assertTrue(self.base_dispatch_controller.has_incoming_transactions())
        self.assertTrue(self.base_dispatch_controller.has_incoming_transactions(RegisteredSubject))
        #dispatch the container
        self.assertRaises(PendingTransactionError, self.base_dispatch_controller.dispatch_user_container_as_json, self.test_container)
        # fake consume outgoing transaction
        OutgoingTransaction.objects.using(self.using_destination).all().update(is_consumed=True)
        #assert consumed
        self.assertFalse(self.base_dispatch_controller.has_outgoing_transactions())
        # assert that a dispatch_model_as_json still fails due to pending incoming transactions
        self.assertRaises(PendingTransactionError, self.base_dispatch_controller.dispatch_user_container_as_json, self.test_container)
        # confirm no pending outgoing
        self.assertFalse(self.base_dispatch_controller.has_outgoing_transactions())
        # fake consume incoming transaction
        IncomingTransaction.objects.all().update(is_consumed=True)
        # assert has no outgoing
        self.assertFalse(self.base_dispatch_controller.has_incoming_transactions())
        # assert there are no pending incoming transactions
        self.assertFalse(self.base_dispatch_controller.has_incoming_transactions(RegisteredSubject))
        # assert there are no pending transactions
        self.assertFalse(self.base_dispatch_controller.has_pending_transactions(RegisteredSubject))
        self.base_dispatch_controller = None

    def test_dispatch_methods_p2(self):
        """Tests dispatching three related models."""
        self.base_dispatch_controller = None
        TestItemThree.objects.all().delete()
        TestItemThree.objects.using(self.using_destination).all().delete()
        TestItemTwo.objects.all().delete()
        TestItemTwo.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        OutgoingTransaction.objects.using(self.using_destination).all().delete()
        OutgoingTransaction.objects.all().delete()
        IncomingTransaction.objects.using(self.using_destination).all().delete()
        IncomingTransaction.objects.all().delete()
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        if not self.producer:
            self.create_producer(True)
        if not self.test_container:
            self.create_test_container()
        # create a dispatch controller
        self.base_dispatch_controller = None
        self.create_base_dispatch_controller()
        # dispatch the container
        self.base_dispatch_controller.dispatch_user_container_as_json(self.test_container)
        # create some items
        test_item = TestItem.objects.create(test_item_identifier='TI', test_container=self.test_container)
        test_item_t2a = TestItemTwo.objects.create(test_item_identifier='TI2A', test_item=test_item)
        test_item_t2b = TestItemTwo.objects.create(test_item_identifier='TI2B', test_item=test_item)
        test_item_t3a = TestItemThree.objects.create(test_item_identifier='TI3A', test_item_two=test_item_t2a)
        test_item_t3b = TestItemThree.objects.create(test_item_identifier='TI3B', test_item_two=test_item_t2a)
        test_item_t3c = TestItemThree.objects.create(test_item_identifier='TI3C', test_item_two=test_item_t2a)
        test_item_t3d = TestItemThree.objects.create(test_item_identifier='TI3D', test_item_two=test_item_t2a)
        # attempt to dispatch a mix of models
        self.assertRaises(DispatchItemError, self.base_dispatch_controller.dispatch_user_items_as_json, [test_item, test_item_t2a], self.test_container)
        # dispatch as an instance
        self.base_dispatch_controller.dispatch_user_items_as_json(test_item_t3a, self.test_container)
        # assert test_item_t2a is already dispatched as a foreign key for test_item_t3a
        self.assertRaises(AlreadyDispatched, self.base_dispatch_controller.dispatch_user_items_as_json, test_item_t2a, self.test_container)
        # assert already dispatched as one of three items is dispatched (test_item_t3a)
        self.assertRaises(AlreadyDispatched, self.base_dispatch_controller.dispatch_user_items_as_json, [test_item_t3a, test_item_t3b, test_item_t3c], self.test_container)
        # remove 3a, dispatch as a list
        self.base_dispatch_controller.dispatch_user_items_as_json([test_item_t3b, test_item_t3c], self.test_container)
        # dispatch as a QuerySet, assert already dispatched
        self.assertRaises(AlreadyDispatched, self.base_dispatch_controller.dispatch_user_items_as_json, TestItemThree.objects.all(), self.test_container)
        # dispatch as a QuerySet
        self.base_dispatch_controller.dispatch_user_items_as_json(TestItemThree.objects.filter(test_item_identifier='TI3D'), self.test_container)
        # confirm test_item was dispatched as a foreign key
        self.assertRaises(AlreadyDispatched, self.base_dispatch_controller.dispatch_user_items_as_json, test_item, self.test_container)
        # ... and test_item_2b was not dispatched
        self.base_dispatch_controller.dispatch_user_items_as_json([test_item_t2b], self.test_container)
        # assert all instances are on the destination
        self.assertEquals(TestItem.objects.using(self.using_destination).all().count(), 1)
        self.assertEquals(TestItemTwo.objects.using(self.using_destination).all().count(), 2)
        self.assertEquals(TestItemThree.objects.using(self.using_destination).all().count(), 4)
        # they can all delete normally from the destination and source
        TestItemThree.objects.all().delete()
        TestItemThree.objects.using(self.using_destination).all().delete()
        TestItemTwo.objects.all().delete()
        TestItemTwo.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        self.base_dispatch_controller = None

    def test_dispatch_methods_p4(self):
        self.base_dispatch_controller = None
        TestItemThree.objects.all().delete()
        TestItemThree.objects.using(self.using_destination).all().delete()
        TestItemTwo.objects.all().delete()
        TestItemTwo.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        OutgoingTransaction.objects.using(self.using_destination).all().delete()
        OutgoingTransaction.objects.all().delete()
        IncomingTransaction.objects.using(self.using_destination).all().delete()
        IncomingTransaction.objects.all().delete()
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        if not self.producer:
            self.create_producer(True)
        if not self.test_container:
            self.create_test_container()
        # create a dispatch controller
        self.base_dispatch_controller = None
        self.create_base_dispatch_controller()
        # dispatch the container
        self.base_dispatch_controller.dispatch_user_container_as_json(self.test_container)
        # create some list items
        tl1 = TestList.objects.create(name='1', short_name='1')
        tl2 = TestList.objects.create(name='2', short_name='2')
        tl3 = TestList.objects.create(name='3', short_name='3')
        # relations for TestItemM2M
        test_item = TestItem.objects.create(test_item_identifier='TI', test_container=self.test_container)
        test_item_t2a = TestItemTwo.objects.create(test_item_identifier='TI2A', test_item=test_item)
        test_item_t3a = TestItemThree.objects.create(test_item_identifier='TI3A', test_item_two=test_item_t2a)
        # create instance with the M2M
        test_item_m2m = TestItemM2M.objects.create(test_item_identifier='TM2M', test_item_three=test_item_t3a)
        test_item_m2m.m2m.add(tl1, tl2, tl3)
        self.base_dispatch_controller.dispatch_user_items_as_json(test_item_m2m, self.test_container)
        # assert test_item_m2m exist on destination
        self.assertEquals(TestItemM2M.objects.using(self.using_destination).all().count(), 1)
        # assert TestList exist on destination
        self.assertEquals(TestList.objects.using(self.using_destination).all().count(), 3)
        # assert instance exists on destination
        dst_test_item_m2m = TestItemM2M.objects.using(self.using_destination).get(test_item_identifier='TM2M')
        self.assertIsNotNone(dst_test_item_m2m)
        # assert that the M2M is populated with three items
        self.assertEquals(dst_test_item_m2m.m2m.all().count(), 3)
        TestItem.objects.all().delete()
        TestList.objects.all().delete()
        TestItemTwo.objects.all().delete()
        TestItemThree.objects.all().delete()
        TestItemM2M.objects.all().delete()
        # re-assert, after deleting source data, requery destination and confirm
        dst_test_item_m2m = TestItemM2M.objects.using(self.using_destination).get(test_item_identifier='TM2M')
        self.assertEquals(dst_test_item_m2m.m2m.all().count(), 3)
        self.base_dispatch_controller = None

    def test_dispatch_methods_p5(self):
        self.base_dispatch_controller = None
        Producer.objects.all().delete()
        TestItemThree.objects.all().delete()
        TestItemThree.objects.using(self.using_destination).all().delete()
        TestItemTwo.objects.all().delete()
        TestItemTwo.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        DispatchItemRegister.objects.all().delete()
        DispatchItemRegister.objects.using(self.using_destination).all().delete()
        DispatchContainerRegister.objects.all().delete()
        DispatchContainerRegister.objects.using(self.using_destination).all().delete()
        self.create_producer(True)
        self.create_test_container()
        OutgoingTransaction.objects.using(self.using_destination).all().delete()
        OutgoingTransaction.objects.all().delete()
        IncomingTransaction.objects.using(self.using_destination).all().delete()
        IncomingTransaction.objects.all().delete()

        self.create_base_dispatch_controller()
        self.base_dispatch_controller.dispatch_user_container_as_json(self.test_container)
        self.assertEquals(OutgoingTransaction.objects.using(self.using_source).filter(is_consumed=False).count(), 0)
        # create some items
        test_item = TestItem.objects.create(test_item_identifier='TI', test_container=self.test_container)
        test_item_t2a = TestItemTwo.objects.create(test_item_identifier='TI2A', test_item=test_item)
        test_item_t2b = TestItemTwo.objects.create(test_item_identifier='TI2B', test_item=test_item)
        test_item_t3a = TestItemThree.objects.create(test_item_identifier='TI3A', test_item_two=test_item_t2a)
        test_item_t3b = TestItemThree.objects.create(test_item_identifier='TI3B', test_item_two=test_item_t2a)
        test_item_t3c = TestItemThree.objects.create(test_item_identifier='TI3C', test_item_two=test_item_t2a)
        test_item_t3d = TestItemThree.objects.create(test_item_identifier='TI3D', test_item_two=test_item_t2a)
        # assert that outgoing transactions were created (2 for each -- one for model, one for audit)
        #print [o.tx_name for o in OutgoingTransaction.objects.using(self.using_destination).filter(is_consumed=False)]
        self.assertEquals(OutgoingTransaction.objects.using(self.using_source).filter(is_consumed=False).count(), 14)
        self.base_dispatch_controller = None

#        #print [rs for rs in RegisteredSubject.objects.all().order_by('id')]
#        rs_pks = [rs.pk for rs in RegisteredSubject.objects.all().order_by('id')]
#        # assert controller not ready, container not dispatched
#
#        # dispatch
#        self.base_dispatch_controller.dispatch_user_items_as_json(TestItemThree.objects.all(), self.test_container)
#        # assert dispatch_as_json does not create any sync transactions
#        self.assertEquals(OutgoingTransaction.objects.filter(is_consumed=False).count(), 8)
#        # assert that RegisteredSubject instance is already dispatched
#        registered_subject = RegisteredSubject.objects.get(subject_identifier=subject_identifiers[0])
#        self.assertRaises(AlreadyDispatchedItem, registered_subject.save)
#        self.assertEquals(OutgoingTransaction.objects.filter(is_consumed=False).count(), 6)
#        # get a return controller
#        return_controller = ReturnController(self.using_source, self.using_destination)
#        self.assertTrue(return_controller.return_dispatched_items(RegisteredSubject.objects.filter(subject_identifier__in=subject_identifiers)))
#        # assert returning items did not create any Outgoing tx
#        self.assertEquals(OutgoingTransaction.objects.filter(is_consumed=False).count(), 6)
#        # assert default can save RegisteredSubject (no longer dispatched)
#        self.assertIsNone(registered_subject.save())
#        # assert this save create two new OutgoingTransactions
#        self.assertEquals(OutgoingTransaction.objects.filter(is_consumed=False).count(), 8)
#        # assert RegisteredSubject instances were dispatched
#        # ... by subject_identifier
#        self.assertEqual([rs.subject_identifier for rs in RegisteredSubject.objects.using(self.using_destination).all().order_by('subject_identifier')], subject_identifiers)
#        # .. by pk
#        self.assertEqual([rs.pk for rs in RegisteredSubject.objects.using(self.using_destination).all().order_by('id')], rs_pks)
#        # confirm no transactions were created that concern this producer
#        self.assertFalse(self.base_dispatch_controller.has_pending_transactions(RegisteredSubject))
#        # assert that serialize on save signal was disconnected and did not create outgoing transactions
#        # on source while dispatching_model_to_json
#        self.assertEquals(OutgoingTransaction.objects.filter(is_consumed=False).count(), 8)
#        # modify a registered subject on the source to create a transaction on the source
#        registered_subject = RegisteredSubject.objects.get(subject_identifier=subject_identifiers[0])
#        registered_subject.registration_status = 'CONSENTED'
#        registered_subject.save()
#        # assert transactions were created by modifying registered_subject
#        self.assertEquals(OutgoingTransaction.objects.filter(is_consumed=False).count(), 10)
#        # assert that the transaction is not from the producer
#        self.assertFalse(self.base_dispatch_controller.has_pending_transactions(RegisteredSubject))
#        # modify a registered subject on the destination to create a transaction on the destination
#        registered_subject = RegisteredSubject.objects.using(self.using_destination).get(subject_identifier=subject_identifiers[0])
#        registered_subject.registration_status = 'CONSENTED'
#        registered_subject.save(using=self.using_destination)
#        # assert transactions were created by modifying registered_subject
#        print '!!warning assert skipped. Have NOT confirmed that Outgoing Transactions are created according to the using argument.'
#        #self.assertEquals(OutgoingTransaction.objects.using(self.using_destination).filter(is_consumed=False).count(), 13)
#        RegisteredSubject.objects.all().delete()
#        RegisteredSubject.objects.using(self.using_destination).all().delete()
#        self.base_dispatch_controller = None

    def test_dispatch_item_within_container(self):
        """Tests dispatching a test container and or a test item and verifies the model method is_dispatched behaves as expected."""
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        self.create_producer(True)
        # create a test container model e.g. Household
        self.create_test_container()
        # assert that it is not dispatched
        self.assertFalse(self.test_container.is_dispatched_as_container())
        self.assertFalse(self.test_container.is_dispatched_as_item())
        # create a test item for the container
        self.create_test_item()
        # assert it is not dispatched
        self.assertFalse(self.test_item.is_dispatched_as_container())
        self.assertFalse(self.test_item.is_dispatched_as_item())
        # get a dispatch controller
        #print registered_controllers._register
        self.base_dispatch_controller = None
        #print registered_controllers._register
        self.create_base_dispatch_controller()
        self.assertEquals(DispatchContainerRegister.objects.all().count(), 1)
        pk = DispatchContainerRegister.objects.all()[0].pk
        obj_id = id(self.base_dispatch_controller)
        # assert user container is dispatched as a container but not an item
        self.assertTrue(self.test_container.is_dispatched_as_container())
        self.assertFalse(self.test_container.is_dispatched_as_item())
        # assert a new controller does not create a new DispatchContainerRegister for the same user container
        self.base_dispatch_controller = None
        base_dispatch_controller = self.base_dispatch_controller = BaseDispatchController(
            self.using_source,
            self.using_destination,
            self.user_container_app_label,
            self.user_container_model_name,
            self.user_container_identifier_attrname,
            self.user_container_identifier)
        # ...still just one
        self.assertEquals(DispatchContainerRegister.objects.all().count(), 1)
        # assert this is still the same DispatchContainerRegister as before
        self.assertEqual(pk, DispatchContainerRegister.objects.all()[0].pk)
        # ... but from a new instance of the controller
        #self.assertNotEqual(obj_id, id(base_dispatch_controller))
        # dispatch the test_container pnly
        base_dispatch_controller.dispatch_user_container_as_json(self.test_container)
        # assert it is now dispatched both as a container and item
        self.assertTrue(self.test_container.is_dispatched_as_container())
        self.assertTrue(self.test_container.is_dispatched_as_item())
        # assert that the TestItem is now evaluated as dispatched only because it's container is dispatched
        self.assertTrue(self.test_item.is_dispatched_as_item())
        # assert that is not dispatched if you do not consider the user_container (is dispatched within a container)
        self.assertFalse(self.test_item.is_dispatched_as_item(user_container=self.test_container))
        self.assertFalse(self.test_item.is_dispatched_as_container())
        # assert only one DispatchItemRegister exists
        self.assertEqual(DispatchItemRegister.objects.all().count(), 1)
        # ... and that it belongs to the user container (TestContainer)
        self.assertEqual(DispatchItemRegister.objects.filter(item_pk=self.test_container.pk).count(), 1)
        # assert that trying to dispatch the user container again fails
        self.assertRaises(AlreadyDispatchedContainer, base_dispatch_controller.dispatch_user_container_as_json, self.test_container)
        # dispatch the TestItem within this user_container
        base_dispatch_controller.dispatch_user_items_as_json([self.test_item], self.test_container)
        # assert that is dispatched
        self.assertTrue(self.test_item.is_dispatched_as_item())
        # assert still returns that it is dispatched even when trying to skip the container test
        self.assertTrue(self.test_item.is_dispatched_as_item(user_container=self.test_container))
        # assert TestItem exists on destination
        self.assertEquals(TestItem.objects.using(self.using_destination).filter(test_item_identifier=self.user_container_identifier).count(), 1)  # used same identifier on both models
        # assert TestContainer exists on destination
        self.assertEquals(TestContainer.objects.using(self.using_destination).filter(test_container_identifier=self.user_container_identifier).count(), 1)
        # get a return controller
        return_controller = ReturnController(self.using_source, self.using_destination)
        # return the dispatched items
        return_controller.return_dispatched_items()
        # assert that container is no longer dispatched
        self.assertFalse(self.test_container.is_dispatched_as_container())
        self.assertFalse(self.test_container.is_dispatched_as_item())
        # assert that the DispatchContainerRegister is no longer dispatched
        self.assertFalse(DispatchContainerRegister.objects.get(pk=pk).is_dispatched)
        # assert that the test item is not dispatched (since the container is no longer dispatched)
        self.assertFalse(self.test_item.is_dispatched_as_item())
        # assert that base_dispatch_controller can no longer be used for dispatch, since the DispatchContainerRegister is returned
        self.assertRaises(DispatchControllerNotReady, base_dispatch_controller.dispatch_user_items_as_json, [self.test_item], self.test_container)
        # create a new controller
        base_dispatch_controller = None
        self.create_base_dispatch_controller()
        # assert a new DispatchContainerRegister was created
        self.assertEquals(DispatchContainerRegister.objects.all().count(), 2)
        # dispatch the user container
        self.base_dispatch_controller.dispatch_user_container_as_json(self.test_container)
        # assert test_container is dispatched
        self.assertTrue(self.test_container.is_dispatched_as_container())
        # assert the test item is dispatched
        self.assertTrue(self.test_item.is_dispatched_as_item())
        # return dispatched items
        return_controller.return_dispatched_items()
        # re-assert nothing is dispatched
        self.assertFalse(self.test_container.is_dispatched_as_container())
        self.assertFalse(self.test_item.is_dispatched_as_item())
        self.base_dispatch_controller = None

    def test_models(self):
        self.create_test_container()
        self.assertRegexpMatches(str(self.test_container.pk), r'[\w]{8}-[\w]{4}-[\w]{4}-[\w]{4}-[\w]{12}')
        self.create_test_item()
        self.assertRegexpMatches(str(self.test_item.pk), r'[\w]{8}-[\w]{4}-[\w]{4}-[\w]{4}-[\w]{12}')

    def test_dispatch_item_and_container(self):
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        if not self.producer:
            self.create_producer(True)
        self.create_test_item()
        # create base controller instance
        self.base_dispatch_controller = None
        # attempt to create instance using TestItem instead of TestContainer
        # assert raise error as TestItem is not a container model
        self.assertRaises(DispatchError, self.create_base_dispatch_controller, 'testitem')
        # create a new dispatch controller
        self.base_dispatch_controller = None
        self.create_base_dispatch_controller()
        # get the DispatchContanier instance
        dispatch_container_register = self.base_dispatch_controller.get_container_register_instance()
        self.assertIsInstance(dispatch_container_register, DispatchContainerRegister)
        # get the model that is being used as a container using information from DispatchContainerRegister
        obj_cls = get_model(
            self.base_dispatch_controller.get_container_register_instance().container_app_label,
            self.base_dispatch_controller.get_container_register_instance().container_model_name)
        # assert that it is our container
        self.assertTrue(issubclass(obj_cls, TestContainer))
        # get it back, in this case is TestContainer
        user_container = obj_cls.objects.get(**{dispatch_container_register.container_identifier_attrname: self.base_dispatch_controller.get_container_register_instance().container_identifier})
        # assert it is an instance of TestContainer
        self.assertIsInstance(user_container, TestContainer)
        self.assertFalse(user_container.is_dispatched_as_item())
        # dispatch the TestContainer instance
        self.base_dispatch_controller.dispatch_user_container_as_json(user_container)
        # assert that the item was dispacthed to its destination
        self.assertIsInstance(user_container.__class__.objects.using(self.base_dispatch_controller.get_using_destination()).get(pk=user_container.pk), user_container.__class__)
        # assert that the disptched item was tracked in DispatchItemRegister
        self.assertEqual(DispatchItemRegister.objects.all().count(), 1)
        self.assertTrue(DispatchItemRegister.objects.get(item_pk=user_container.pk).is_dispatched)
        # requery for the container instance (Necessary??)
        user_container = obj_cls.objects.get(**{self.base_dispatch_controller.get_container_register_instance().container_identifier_attrname: self.base_dispatch_controller.get_container_register_instance().container_identifier})
        #self.assertTrue(obj.is_dispatched)
        self.assertTrue(user_container.is_dispatched_as_container())
        # assert that you cannot dispatch it again
        self.assertRaises(AlreadyDispatchedContainer, self.base_dispatch_controller.dispatch_user_container_as_json, user_container)
        dispatch_item_register = DispatchItemRegister.objects.get(item_pk=user_container.pk)
        # flag is dispatched as False
        dispatch_item_register.is_dispatched = False
        dispatch_item_register.return_datetime = datetime.today()
        dispatch_item_register.save()
        # dispatch again ...
        self.assertIsNone(self.base_dispatch_controller.dispatch_user_container_as_json(user_container))
        # assert that a the existing dispatch item was edited (uses get_or_create)
        self.assertEqual(DispatchItemRegister.objects.all().count(), 1)
        self.assertEqual(DispatchItemRegister.objects.filter(is_dispatched=True, return_datetime__isnull=True).count(), 1)
        #DispatchItemRegister.objects.all().delete()
        self.base_dispatch_controller = None
