from __future__ import absolute_import

import logging

from sentry.api.base import Endpoint
from sentry.api.bases.project import ProjectPermission
from sentry.api.exceptions import ResourceDoesNotExist
from sentry.utils.sdk import configure_scope
from sentry.models import Group, GroupStatus, get_group_with_redirect

logger = logging.getLogger(__name__)

EXCLUDED_STATUSES = (
    GroupStatus.PENDING_DELETION, GroupStatus.DELETION_IN_PROGRESS, GroupStatus.PENDING_MERGE
)


class GroupPermission(ProjectPermission):
    scope_map = {
        'GET': ['event:read', 'event:write', 'event:admin'],
        'POST': ['event:write', 'event:admin'],
        'PUT': ['event:write', 'event:admin'],
        'DELETE': ['event:admin'],
    }

    def has_object_permission(self, request, view, group):
        return super(GroupPermission, self).has_object_permission(request, view, group.project)


class GroupEndpoint(Endpoint):
    permission_classes = (GroupPermission, )

    def convert_args(self, request, issue_id, *args, **kwargs):
        # TODO(tkaemming): Ideally, this would return a 302 response, rather
        # than just returning the data that is bound to the new group. (It
        # technically shouldn't be a 301, since the response could change again
        # as the result of another merge operation that occurs later. This
        # wouldn't break anything though -- it will just be a "permanent"
        # redirect to *another* permanent redirect.) This would require
        # rebuilding the URL in one of two ways: either by hacking it in with
        # string replacement, or making the endpoint aware of the URL pattern
        # that caused it to be dispatched, and reversing it with the correct
        # `issue_id` keyword argument.
        try:
            group, _ = get_group_with_redirect(
                issue_id,
                queryset=Group.objects.select_related('project', 'project__organization'),
            )
        except Group.DoesNotExist:
            raise ResourceDoesNotExist

        self.check_object_permissions(request, group)

        with configure_scope() as scope:
            scope.set_tag("project", group.project_id)
            scope.set_tag("organization", group.project.organization_id)

        if group.status in EXCLUDED_STATUSES:
            raise ResourceDoesNotExist

        request._request.organization = group.project.organization

        kwargs['group'] = group

        return (args, kwargs)
