# -*- coding: utf-8 -*-
#
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from django.db.models import Q
from django.utils.decorators import method_decorator

from common.exceptions import SomeoneIsDoingThis
from common.permissions import IsValidUser
from common.utils.django import get_object_or_none
from common.utils import get_logger
from .user_permission_nodes import UserGrantedNodesAsTreeApi
from .user_permission_nodes import UserGrantedNodeChildrenAsTreeApi
from .mixin import DispatchUserGrantedNodeMixin
from perms.models import MappingNode
from perms.utils import check_user_mapping_node_task
from assets.models import Node, Asset
from assets.api import SerializeToTreeNodeMixin
from perms.exceptions import AdminIsModifyingPerm
from orgs.utils import tmp_to_root_org

logger = get_logger(__name__)

__all__ = [
    'UserGrantedNodesAsTreeApi',
    'UserGrantedNodeChildrenAsTreeApi',
    'UserGrantedNodeChildrenWithAssetsAsTreeApi',
    'UserGrantedNodeChildrenApi',
]


class UserGrantedNodeChildrenWithAssetsAsTreeApi(SerializeToTreeNodeMixin, ListAPIView):
    permission_classes = (IsValidUser, )

    def list(self, request: Request, *args, **kwargs):
        user = request.user
        key = request.query_params.get('key')
        try:
            check_user_mapping_node_task(user)
        except SomeoneIsDoingThis:
            raise AdminIsModifyingPerm

        nodes = []
        assets = []
        if not key:
            root_node = Node.objects.filter(
                mapping_nodes__user=user,
                mapping_nodes__granted_ref_count__gt=0
            ).get(parent_key='')
            nodes.append(root_node)
        else:
            mapping_node: MappingNode = get_object_or_none(
                MappingNode, user=user, key=key, granted_ref_count__gt=0)
            if mapping_node is None:
                nodes = Node.objects.filter(parent_key=key)
                assets = Asset.objects.filter(nodes__key=key).distinct()
            else:
                if mapping_node.granted:
                    nodes = Node.objects.filter(parent_key=key)
                    assets = Asset.objects.filter(nodes__key=key).distinct()
                else:
                    nodes = Node.objects.filter(
                        mapping_nodes__parent_key=key,
                        mapping_nodes__user=user,
                        mapping_nodes__granted_ref_count__gt=0
                    ).distinct()
                    if mapping_node.asset_granted_ref_count > 0:
                        assets = Asset.objects.filter(
                            nodes__key=key,
                        ).filter(Q(granted_by_permissions__users=user)|Q(granted_by_permissions__user_groups__users=user))

        nodes = self.serialize_nodes(nodes)
        assets = self.serialize_assets(assets, key)
        return Response(data=[*nodes, *assets])


@method_decorator(tmp_to_root_org(), name='list')
class UserGrantedNodeChildrenApi(DispatchUserGrantedNodeMixin, SerializeToTreeNodeMixin, ListAPIView):
    permission_classes = (IsValidUser, )

    def list(self, request: Request, *args, **kwargs):

        user = request.user
        key = request.query_params.get('key')

        try:
            check_user_mapping_node_task(user)
        except SomeoneIsDoingThis:
            raise AdminIsModifyingPerm

        if not key:
            nodes = Node.objects.filter(
                mapping_nodes__user=user,
                mapping_nodes__granted_ref_count__gt=0,
                parent_key=''
            )
        else:
            mapping_node = get_object_or_none(
                MappingNode, user=user, key=key, granted_ref_count__gt=0
            )
            nodes = self.dispatch_node_process(key, mapping_node, None)
        nodes = self.serialize_nodes(nodes)
        return Response(data=nodes)

    def on_granted_node(self, key, mapping_node: MappingNode, node: Node = None):
        return Node.objects.filter(parent_key=key)

    def on_ungranted_node(self, key, mapping_node: MappingNode, node: Node = None):
        user = self.request.user
        return Node.objects.filter(
            parent_key=key,
            mapping_nodes__user=user,
            mapping_nodes__granted_ref_count__gt=0
        ).distinct()
