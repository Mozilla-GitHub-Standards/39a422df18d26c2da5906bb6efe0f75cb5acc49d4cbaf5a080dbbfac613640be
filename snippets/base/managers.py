from datetime import datetime

from django.db.models import Manager
from django.db.models.query import QuerySet

from product_details import product_details

from snippets.base.util import first


LANGUAGE_VALUES = [key.lower() for key in product_details.languages.keys()]


class ClientMatchRuleQuerySet(QuerySet):
    def evaluate(self, client):
        passed_rules, failed_rules = [], []
        for rule in self:
            if rule.matches(client):
                passed_rules.append(rule)
            else:
                failed_rules.append(rule)
        return passed_rules, failed_rules


class ClientMatchRuleManager(Manager):
    def get_queryset(self):
        return ClientMatchRuleQuerySet(self.model)


class SnippetQuerySet(QuerySet):
    def filter_by_available(self):
        """Datetime filtering of snippets.

        Filter by date in python to avoid caching based on the passing
        of time.
        """
        now = datetime.utcnow()
        matching_snippets = [
            snippet for snippet in self if
            (not snippet.publish_start or snippet.publish_start <= now) and
            (not snippet.publish_end or snippet.publish_end >= now)
        ]
        return matching_snippets

    def match_client(self, client):
        from snippets.base.models import CHANNELS, JSONSnippet, ClientMatchRule

        filters = {}

        # Retrieve the first channel that starts with the client's channel.
        # Allows things like "release-cck-mozilla14" to match "release".
        if client.channel == 'default':
            client_channel = 'nightly'
        else:
            client_channel = first(CHANNELS, client.channel.startswith)

        if client_channel:
            filters.update(**{'on_{0}'.format(client_channel): True})

        startpage_field = 'on_startpage_{0}'.format(client.startpage_version)
        if hasattr(self.model, startpage_field):
            filters.update(
                **{startpage_field: True})

        # Only filter by locale if they pass a valid locale.
        locales = list(filter(client.locale.lower().startswith, LANGUAGE_VALUES))
        if locales:
            filters.update(locales__code__in=locales)
        else:
            # If the locale is invalid, only match snippets with no
            # locales specified.
            filters.update(locales__isnull=True)

        snippets = self.filter(**filters).distinct()
        if issubclass(self.model, JSONSnippet):
            filtering = {'jsonsnippet__in': snippets}
        else:
            filtering = {'snippet__in': snippets}

        # Filter based on ClientMatchRules
        passed_rules, failed_rules = (ClientMatchRule.objects
                                      .filter(**filtering)
                                      .distinct()
                                      .evaluate(client))

        return snippets.exclude(client_match_rules__in=failed_rules)


class SnippetManager(Manager):
    def get_queryset(self):
        return SnippetQuerySet(self.model)

    def match_client(self, client):
        return self.get_queryset().match_client(client)


class ASRSnippetQuerySet(QuerySet):
    def filter_by_available(self):
        """Datetime filtering of snippets.

        Filter by date in python to avoid caching based on the passing
        of time.
        """
        now = datetime.utcnow()
        matching_snippets = [
            snippet for snippet in self if
            (not snippet.publish_start or snippet.publish_start <= now) and
            (not snippet.publish_end or snippet.publish_end >= now)
        ]
        return matching_snippets

    def match_client(self, client):
        from snippets.base.models import CHANNELS, ClientMatchRule, Target

        snippet_filters = {}
        target_filters = {}

        # Retrieve the first channel that starts with the client's channel.
        # Allows things like "release-cck-mozilla14" to match "release".
        if client.channel == 'default':
            client_channel = 'nightly'
        else:
            client_channel = first(CHANNELS, client.channel.startswith)
        if client_channel:
            target_filters.update(**{'on_{0}'.format(client_channel): True})
        targets = Target.objects.filter(**target_filters).distinct()

        # Only filter by locale if they pass a valid locale.
        locales = list(filter(client.locale.lower().startswith, LANGUAGE_VALUES))
        if locales:
            snippet_filters.update(locales__code__in=locales)
        else:
            # If the locale is invalid, only match snippets with no
            # locales specified.
            snippet_filters.update(locales__isnull=True)

        snippets = self.filter(**snippet_filters).filter(targets__in=targets)

        # Filter based on ClientMatchRules
        passed_rules, failed_rules = (ClientMatchRule.objects
                                      .filter(target__asrsnippet__in=snippets)
                                      .distinct()
                                      .evaluate(client))

        return snippets.exclude(targets__client_match_rules__in=failed_rules)


class ASRSnippetManager(Manager):
    def get_queryset(self):
        return ASRSnippetQuerySet(self.model)

    def match_client(self, client):
        return self.get_queryset().match_client(client)
