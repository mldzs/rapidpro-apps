from datetime import datetime

from django.contrib.auth.models import User
from django_grpc_framework.test import FakeRpcError, RPCTransactionTestCase
from rest_framework.exceptions import ValidationError

from temba.orgs.models import Org
from weni.org_grpc.grpc_gen import org_pb2, org_pb2_grpc
from weni.org_grpc.serializers import SerializerUtils


class OrgServiceTest(RPCTransactionTestCase):

    WRONG_ID = -1

    def setUp(self):

        User.objects.create_user(username="testuser", password="123", email="test@weni.ai")
        User.objects.create_user(username="weniuser", password="123", email="wene@user.com")

        user = User.objects.get(username="testuser")

        Org.objects.create(name="Temba", timezone="Africa/Kigali", created_by=user, modified_by=user)
        Org.objects.create(name="Weni", timezone="Africa/Kigali", created_by=user, modified_by=user)
        Org.objects.create(name="Test", timezone="Africa/Kigali", created_by=user, modified_by=user)

        super().setUp()

        self.stub = org_pb2_grpc.OrgControllerStub(self.channel)

    def test_serializer_utils(self):
        user = User.objects.last()

        with self.assertRaisesMessage(ValidationError, (f"User: {self.WRONG_ID} not found!")):
            SerializerUtils.get_object(User, self.WRONG_ID)

        self.assertEquals(user, SerializerUtils.get_object(User, user.pk))

    def test_list_orgs(self):

        with self.assertRaises(FakeRpcError):
            for org in self.stub_org_list_request():
                ...

        with self.assertRaises(FakeRpcError):
            for org in self.stub_org_list_request(user_email="wrong@email.com"):
                ...

        orgs = Org.objects.all()
        user = User.objects.get(username="testuser")

        self.assertEquals(self.get_orgs_count(user), 0)

        orgs[0].administrators.add(user)
        self.assertEquals(self.get_orgs_count(user), 1)

        orgs[1].viewers.add(user)
        self.assertEquals(self.get_orgs_count(user), 2)

        orgs[2].editors.add(user)
        self.assertEquals(self.get_orgs_count(user), 3)

    def test_list_users_on_org(self):
        org = Org.objects.get(name="Temba")

        testuser = User.objects.get(username="testuser")
        weniuser = User.objects.get(username="weniuser")

        org.administrators.add(testuser)
        self.assertEquals(self.get_org_users_count(testuser), 1)

        org.administrators.add(weniuser)
        self.assertEquals(self.get_org_users_count(testuser), 2)

    def test_create_org(self):
        org_name = "TestCreateOrg"
        user = User.objects.first()

        with self.assertRaises(ValidationError):
            self.stub.Create(org_pb2.OrgCreateRequest(name=org_name, timezone="Africa/Kigali", user_id=self.WRONG_ID))

        with self.assertRaises(ValidationError):
            self.stub.Create(org_pb2.OrgCreateRequest(name=org_name, timezone="Wrong/Zone", user_id=user.id))

        self.stub.Create(org_pb2.OrgCreateRequest(name=org_name, timezone="Africa/Kigali", user_id=user.id))

        orgs = Org.objects.filter(name=org_name)
        org = orgs.first()

        self.assertEquals(len(orgs), 1)

        created_by = org.created_by
        modified_by = org.modified_by

        self.assertEquals(created_by, user)
        self.assertEquals(modified_by, user)

    def test_destroy_org(self):
        org = Org.objects.last()
        is_active = org.is_active
        modified_by = org.modified_by

        with self.assertRaisesMessage(FakeRpcError, f"User: {self.WRONG_ID} not found!"):
            self.stub.Destroy(org_pb2.OrgDestroyRequest(id=org.id, user_id=self.WRONG_ID))

        weniuser = User.objects.get(username="weniuser")

        with self.assertRaisesMessage(FakeRpcError, f"Org: {self.WRONG_ID} not found!"):
            self.stub.Destroy(org_pb2.OrgDestroyRequest(id=self.WRONG_ID, user_id=weniuser.id))

        self.stub.Destroy(org_pb2.OrgDestroyRequest(id=org.id, user_id=weniuser.id))

        destroyed_org = Org.objects.get(id=org.id)

        self.assertFalse(destroyed_org.is_active)
        self.assertNotEquals(is_active, destroyed_org.is_active)
        self.assertEquals(weniuser, destroyed_org.modified_by)
        self.assertNotEquals(modified_by, destroyed_org.modified_by)

    def test_update_org(self):
        org = Org.objects.first()
        user = User.objects.first()

        permission_error_message = f"User: {user.id} has no permission to update Org: {org.id}"

        with self.assertRaisesMessage(ValidationError, permission_error_message):
            self.stub.Update(org_pb2.OrgUpdateRequest(id=org.id, user_id=user.id))

        with self.assertRaisesMessage(ValidationError, "User: 0 not found!"):
            self.stub.Update(org_pb2.OrgUpdateRequest(id=org.id))

        user.is_superuser = True
        user.save()

        org.administrators.add(user)

        update_fields = {
            "name": "NewOrgName",
            "timezone": "America/Maceio",
            "date_format": "M",
            "plan": "test",
            "plan_end": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brand": "push.ia",
            "is_anon": True,
            "is_multi_user": True,
            "is_multi_org": True,
            "is_suspended": True,
        }

        self.stub.Update(org_pb2.OrgUpdateRequest(id=org.id, user_id=user.id, **update_fields))

        updated_org = Org.objects.get(pk=org.pk)

        self.assertEquals(update_fields.get("name"), updated_org.name)
        self.assertNotEquals(org.name, updated_org.name)

        self.assertEquals(update_fields.get("timezone"), str(updated_org.timezone))
        self.assertNotEquals(org.timezone, updated_org.timezone)

        self.assertEquals(update_fields.get("date_format"), updated_org.date_format)
        self.assertNotEquals(org.date_format, updated_org.date_format)

        self.assertEquals(update_fields.get("plan"), updated_org.plan)
        self.assertNotEquals(org.plan, updated_org.plan)

        self.assertEquals(
            update_fields.get("plan_end"), updated_org.plan_end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.assertNotEquals(org.plan_end, updated_org.plan_end)

        self.assertEquals(update_fields.get("brand"), updated_org.brand)
        self.assertNotEquals(org.brand, updated_org.brand)

        self.assertEquals(update_fields.get("is_anon"), updated_org.is_anon)
        self.assertNotEquals(org.is_anon, updated_org.is_anon)

        self.assertEquals(update_fields.get("is_multi_user"), updated_org.is_multi_user)
        self.assertNotEquals(org.is_multi_user, updated_org.is_multi_user)

        self.assertEquals(update_fields.get("is_multi_org"), updated_org.is_multi_org)
        self.assertNotEquals(org.is_multi_org, updated_org.is_multi_org)

        self.assertEquals(update_fields.get("is_suspended"), updated_org.is_suspended)
        self.assertNotEquals(org.is_suspended, updated_org.is_suspended)

    def get_org_users_count(self, user: User) -> int:
        orgs = self.get_user_orgs(user)
        org = next(orgs)
        return len(org.users)

    def get_orgs_count(self, user: User) -> int:
        return len(list(self.get_user_orgs(user)))

    def get_user_orgs(self, user: User):
        return self.stub_org_list_request(user_email=user.email)

    def stub_org_list_request(self, **kwargs):
        return self.stub.List(org_pb2.OrgListRequest(**kwargs))
