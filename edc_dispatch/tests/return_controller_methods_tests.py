from django.db.models import get_model
from edc.device.sync.exceptions import ProducerError
from edc.device.sync.models import OutgoingTransaction
from edc.device.sync.classes import Consumer
from ..exceptions import (AlreadyDispatchedContainer, AlreadyDispatchedItem, DispatchContainerError,
                          DispatchModelError, DispatchControllerNotReady, DispatchItemError)
from ..models import TestItem, DispatchItemRegister, DispatchContainerRegister, TestContainer
from ..classes import ReturnController, BaseDispatchController
from .base_controller_tests import BaseControllerTests


class ReturnControllerMethodsTests(BaseControllerTests):

    def test_return_controller_p1(self):
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        DispatchContainerRegister.objects.all().delete()
        DispatchItemRegister.objects.all().delete()
        OutgoingTransaction.objects.all().delete()
        OutgoingTransaction.objects.using(self.using_destination).all().delete()
        self.create_producer(is_active=True)
        self.create_test_item()
        # assert not instances registered to DispatchItemRegister
        self.assertEqual(DispatchItemRegister.objects.all().count(), 0)
        # assert no TestItem on destination
        self.assertEquals(TestItem.objects.using(self.using_destination).all().count(), 0)
        # get a return controller
        return_controller = ReturnController(self.using_source, self.using_destination)
        # assert still not instances registered to DispatchItemRegister
        self.assertEqual(DispatchItemRegister.objects.all().count(), 0)
        dispatch_container_register = None
        return_controller.return_dispatched_items(dispatch_container_register)
        # assert nothing was dispatched to the producer
        self.assertEquals(TestItem.objects.using(return_controller.get_using_destination()).all().count(), 0)
        self.assertEqual(DispatchItemRegister.objects.all().count(), 0)
        self.create_base_dispatch_controller()
        obj_cls = get_model(
            self.base_dispatch_controller.get_container_register_instance().container_app_label,
            self.base_dispatch_controller.get_container_register_instance().container_model_name)
        dispatch_container_register = self.base_dispatch_controller.get_container_register_instance()
        self.assertIsInstance(dispatch_container_register, DispatchContainerRegister)
        # assert that nothing was dispatched to the producer yet
        self.assertEquals(obj_cls.objects.using(self.base_dispatch_controller.get_using_destination()).filter(**{dispatch_container_register.container_identifier_attrname: self.base_dispatch_controller.get_container_register_instance().container_identifier}).count(), 0)
        # assert no dispatch items yet
        self.assertEqual(DispatchItemRegister.objects.all().count(), 0)
        return_controller.return_dispatched_items(dispatch_container_register)
        self.assertEqual(DispatchItemRegister.objects.all().count(), 0)
        obj = obj_cls.objects.get(**{dispatch_container_register.container_identifier_attrname: self.base_dispatch_controller.get_container_register_instance().container_identifier})
        self.assertEquals(TestItem.objects.using(return_controller.get_using_destination()).all().count(), 0)

        # get a new controller
        # assert 
        TestContainer.objects.all().delete()
        self.base_dispatch_controller = None
        # assert raises error since test container does not exist
        self.assertRaises(DispatchModelError, self.create_base_dispatch_controller)
        # remove reference in model to user container
        self.base_dispatch_controller = None
        # try to initialize without app_label/modename
        self.assertRaises(DispatchModelError, BaseDispatchController, self.using_source, self.using_destination, None, None, '-', '1')
        # try to initialize without app_label/modename/identifier_attrname
        self.assertRaises(AttributeError, BaseDispatchController, self.using_source, self.using_destination, None, None, None, '1')
        # try to initialize without app_label/modename/identifier_attrname/identifier value
        self.assertRaises(AttributeError, BaseDispatchController, self.using_source, self.using_destination, None, None, None, None)
        self.base_dispatch_controller = None

    def test_return_controller_p2(self):
        """Makes various failed attempts to dispatch an item in a container."""
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        DispatchContainerRegister.objects.all().delete()
        DispatchItemRegister.objects.all().delete()
        self.create_test_container()
        # assert fails because can't find producer
        self.assertRaises(ProducerError, self.create_base_dispatch_controller)
        # create the producer
        self.create_producer(is_active=True)
        # ...try again
        self.create_base_dispatch_controller()
        # get the DispatchContainerRegister to try to pass to json
        dispatch_container_register = self.base_dispatch_controller.get_container_register_instance()
        # assert fails because dispatch_container_register cannot be a user container
        self.assertRaises(DispatchContainerError, self.base_dispatch_controller.dispatch_user_container_as_json, dispatch_container_register)
        # dispatch as json the user container
        self.base_dispatch_controller.dispatch_user_container_as_json(self.test_container)
        # assert fails as you cannot use dispatch_container_register as a user_container to dispatch an item
        self.assertRaises(DispatchItemError, self.base_dispatch_controller.dispatch_user_items_as_json, dispatch_container_register, self.test_container)
        # assert Raises dispatch error because user item and user container are same class
        self.assertRaises(DispatchContainerError, self.base_dispatch_controller.dispatch_user_items_as_json, self.test_container, self.test_container)
        # assert fails because container was already dispatched
        self.assertRaises(AlreadyDispatchedContainer, self.base_dispatch_controller.dispatch_user_container_as_json, self.test_container)
        # assert raises error because user item in None
        self.assertRaises(DispatchItemError, self.base_dispatch_controller.dispatch_user_items_as_json, None, self.test_container)
        self.create_test_item()
        self.base_dispatch_controller.dispatch_user_items_as_json(self.test_item, self.test_container)
        # assert dispatch item created for both the test container and test item
        self.assertEqual(DispatchItemRegister.objects.filter(is_dispatched=True).count(), 2)
        self.assertEqual(DispatchItemRegister.objects.filter(item_pk=self.test_item.pk, is_dispatched=True).count(), 1)
        self.assertEqual(DispatchItemRegister.objects.filter(item_pk=self.test_container.pk, is_dispatched=True).count(), 1)
        self.base_dispatch_controller = None

    def test_return_controller_p3(self):
        """Dispatches an item in a container, tries to change the items and verifies changes on return."""
        TestContainer.objects.all().delete()
        TestContainer.objects.using(self.using_destination).all().delete()
        TestItem.objects.all().delete()
        TestItem.objects.using(self.using_destination).all().delete()
        DispatchContainerRegister.objects.all().delete()
        DispatchItemRegister.objects.all().delete()
        OutgoingTransaction.objects.all().delete()
        OutgoingTransaction.objects.using(self.using_destination).all().delete()
        self.create_test_container()
        self.create_test_item()
        self.test_item.comment = 'TEST_COMMENT'
        self.test_item.save()
        self.create_producer(is_active=True)
        self.base_dispatch_controller = None
        # get a new controller
        self.create_base_dispatch_controller()
        # assert DispatchControllerNotReady as the test container has not been dispatched as json to destination
        self.assertRaises(DispatchControllerNotReady, self.base_dispatch_controller.dispatch_user_items_as_json, self.test_item, self.test_container)
        # dispatch to json the container
        self.base_dispatch_controller.dispatch_user_container_as_json(self.test_container)
        # dispatch the item
        self.base_dispatch_controller.dispatch_user_items_as_json(self.test_item, self.test_container)
        # assert dispatch item is updated
        self.assertEqual(DispatchItemRegister.objects.filter(is_dispatched=True, return_datetime__isnull=True, item_pk=self.test_item.pk).count(), 1)
        # assert user_container on the producer
        self.assertEqual(self.test_container.__class__.objects.using(self.base_dispatch_controller.get_using_destination()).all().count(), 1)
        # assert test_item on the producer
        self.assertEqual(self.test_item.__class__.objects.using(self.base_dispatch_controller.get_using_destination()).all().count(), 1)
        # veryfy Dispatch registers before edit and return
        self.assertTrue(self.base_dispatch_controller.get_container_register_instance().is_dispatched)
        self.assertEqual(self.base_dispatch_controller.get_registered_items().count(), 2)
        self.assertEqual(DispatchItemRegister.objects.filter(item_pk=self.test_item.pk, is_dispatched=True).count(), 1)
        self.assertEqual(DispatchItemRegister.objects.filter(item_pk=self.test_container.pk, is_dispatched=True).count(), 1)
        # try to change the item on default and confirm AlreadyDispatchedItem raised
        test_item_identifier = self.base_dispatch_controller.get_user_container_identifier()
        test_item_destination = self.test_item.__class__.objects.using(self.base_dispatch_controller.get_using_destination()).get(test_item_identifier=test_item_identifier)
        test_item_destination.comment = 'TEST_COMMENT_CHANGED'
        # assert AlreadyDispatchedItem on save
        self.assertRaises(AlreadyDispatchedItem, test_item_destination.save)
        # change it on destination
        self.assertIsNone(test_item_destination.save(using=self.base_dispatch_controller.get_using_destination()))
        # return the changed item
        return_controller = ReturnController(self.using_source, self.using_destination)
        # assert fails with PendingTransactionError
        # TODO: why does below not fail??
        #self.assertRaises(PendingTransactionError, return_controller.return_dispatched_items)
        # sync transactions
        consumer = Consumer()
        consumer.fetch_outgoing(self.using_destination)
        # assert fails, try to edit before return
        self.assertRaises(AlreadyDispatchedItem, test_item_destination.save)
        #return
        return_controller.return_dispatched_items
        # confirm the change appears on source test item
        test_item = TestItem.objects.get(test_item_identifier=test_item_identifier)
        # try to change the TestItem again
        self.assertEqual(test_item.comment, 'TEST_COMMENT_CHANGED')
        # assert saving on source will NOT raise any AlreadyDispatched errors
        self.assertIsNone(test_item.save())
        self.base_dispatch_controller = None
