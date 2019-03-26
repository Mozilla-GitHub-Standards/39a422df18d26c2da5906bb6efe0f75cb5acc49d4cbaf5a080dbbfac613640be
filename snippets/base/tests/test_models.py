from django.conf import settings
from django.test.utils import override_settings
from django.urls import reverse

from jinja2 import Markup
from unittest.mock import MagicMock, Mock, patch
from pyquery import PyQuery as pq

from snippets.base.models import (STATUS_CHOICES,
                                  Client,
                                  Icon,
                                  SimpleTemplate,
                                  UploadedFile,
                                  _generate_filename)
from snippets.base.util import fluent_link_extractor
from snippets.base.tests import (ASRSnippetFactory,
                                 ClientMatchRuleFactory,
                                 JSONSnippetFactory,
                                 SearchProviderFactory,
                                 SnippetFactory,
                                 SnippetTemplateFactory,
                                 SnippetTemplateVariableFactory,
                                 TargetFactory,
                                 TestCase,
                                 UserFactory,
                                 UploadedFileFactory)


class DuplicateSnippetMixInTests(TestCase):
    def _dup_test(self, snippet):
        user = UserFactory.create()
        snippet.client_match_rules.add(*ClientMatchRuleFactory.create_batch(3))
        snippet_copy = snippet.duplicate(user)
        self.assertEqual(snippet_copy.published, False)
        self.assertNotEqual(snippet_copy.id, snippet.id)
        self.assertEqual(snippet_copy.locales.count(), 1)
        self.assertTrue(snippet_copy.locales.all()[0] == snippet.locales.all()[0])
        self.assertEqual(set(snippet_copy.client_match_rules.all()),
                         set(snippet.client_match_rules.all()))

        # Only Snippet and not JSONSnippet, has creator
        if hasattr(snippet, 'creator'):
            self.assertNotEqual(snippet_copy.creator, snippet.creator)

    def test_snippet(self):
        snippet = SnippetFactory.create()
        self._dup_test(snippet)

    def test_json_snippet(self):
        snippet = JSONSnippetFactory.create()
        self._dup_test(snippet)


class ClientMatchRuleTests(TestCase):
    def _client(self, **kwargs):
        client_kwargs = dict((key, '') for key in Client._fields)
        client_kwargs.update(kwargs)
        return Client(**client_kwargs)

    def test_string_match(self):
        client = self._client(channel='aurora')
        pass_rule = ClientMatchRuleFactory(channel='aurora')
        fail_rule = ClientMatchRuleFactory(channel='nightly')

        self.assertTrue(pass_rule.matches(client))
        self.assertTrue(not fail_rule.matches(client))

    def test_regex_match(self):
        client = self._client(version='15.2.4')
        pass_rule = ClientMatchRuleFactory(version=r'/[\d\.]+/')
        fail_rule = ClientMatchRuleFactory(version=r'/\D+/')

        self.assertTrue(pass_rule.matches(client))
        self.assertTrue(not fail_rule.matches(client))

    def test_multi_match(self):
        client = self._client(version='1.0', locale='en-US')
        pass_rule = ClientMatchRuleFactory(version='1.0', locale='en-US')
        fail_rule = ClientMatchRuleFactory(version='1.0', locale='fr')

        self.assertTrue(pass_rule.matches(client))
        self.assertTrue(not fail_rule.matches(client))

    def test_empty_match(self):
        client = self._client(version='1.0', locale='fr')
        rule = ClientMatchRuleFactory()

        self.assertTrue(rule.matches(client))

    def test_exclusion_rule_match(self):
        client = self._client(channel='aurora')
        fail_rule = ClientMatchRuleFactory(channel='aurora', is_exclusion=True)
        pass_rule = ClientMatchRuleFactory(channel='nightly',
                                           is_exclusion=True)

        self.assertTrue(pass_rule.matches(client))
        self.assertTrue(not fail_rule.matches(client))


class SnippetTemplateTests(TestCase):
    def test_render(self):
        template = SnippetTemplateFactory(code='<p>{{myvar}}</p>')
        self.assertEqual(template.render({'myvar': 'foo'}), '<p>foo</p>')

    def test_render_snippet_id(self):
        """If the template context doesn't have a snippet_id entry, add one set to 0."""
        template = SnippetTemplateFactory(code='<p>{{ snippet_id }}</p>')
        self.assertEqual(template.render({'myvar': 'foo'}), '<p>0</p>')

    @patch('snippets.base.models.hashlib.sha1')
    @patch('snippets.base.models.JINJA_ENV.from_string')
    def test_render_not_cached(self, mock_from_string, mock_sha1):
        """If the template isn't in the cache, add it."""
        template = SnippetTemplateFactory(code='asdf')
        mock_cache = {}

        with patch('snippets.base.models.template_cache', mock_cache):
            result = template.render({})

        jinja_template = mock_from_string.return_value
        cache_key = mock_sha1.return_value.hexdigest.return_value
        self.assertEqual(mock_cache, {cache_key: jinja_template})

        mock_sha1.assert_called_with(b'asdf')
        mock_from_string.assert_called_with('asdf')
        jinja_template.render.assert_called_with({'snippet_id': 0})
        self.assertEqual(result, jinja_template.render.return_value)

    @patch('snippets.base.models.hashlib.sha1')
    @patch('snippets.base.models.JINJA_ENV.from_string')
    def test_render_cached(self, mock_from_string, mock_sha1):
        """
        If the template is in the cache, use the cached version instead
        of bothering to compile it.
        """
        template = SnippetTemplateFactory(code='asdf')
        cache_key = mock_sha1.return_value.hexdigest.return_value
        jinja_template = Mock()
        mock_cache = {cache_key: jinja_template}

        with patch('snippets.base.models.template_cache', mock_cache):
            result = template.render({})

        mock_sha1.assert_called_with(b'asdf')
        self.assertTrue(not mock_from_string.called)
        jinja_template.render.assert_called_with({'snippet_id': 0})
        self.assertEqual(result, jinja_template.render.return_value)


class SnippetTests(TestCase):
    def test_to_dict(self):
        snippet = SnippetFactory.create(weight=60, campaign='foo-campaign',
                                        countries=['gr', 'it'], client_options={'foo': 'bar'})
        snippet.render = Mock()
        snippet.render.return_value = 'rendered'

        data = {
            'code': 'rendered',
            'client_options': {'foo': 'bar'},
            'campaign': 'foo-campaign',
            'weight': 60,
            'countries': ['gr', 'it'],
            'exclude_from_search_engines': [],
            'id': snippet.id,
            'name': snippet.name,
        }
        self.assertEqual(data, snippet.to_dict())

    def test_render(self):
        template = SnippetTemplateFactory.create()
        template.render = Mock()
        template.render.return_value = '<a href="asdf">qwer</a>'

        data = '{"url": "asdf", "text": "qwer"}'
        snippet = SnippetFactory.create(template=template, data=data,
                                        countries=['us'], weight=60)

        expected = ('<div data-snippet-id="{id}" data-weight="60" data-campaign="" '
                    'class="snippet-metadata" data-countries="us">'
                    '<a href="asdf">qwer</a></div>'.format(id=snippet.id))
        self.assertEqual(snippet.render().strip(), expected)
        template.render.assert_called_with({
            'url': 'asdf',
            'text': 'qwer',
            'snippet_id': snippet.id
        })

    def test_render_campaign(self):
        template = SnippetTemplateFactory.create()
        template.render = Mock()
        template.render.return_value = '<a href="asdf">qwer</a>'

        data = '{"url": "asdf", "text": "qwer"}'
        snippet = SnippetFactory.create(template=template, data=data, campaign='foo')

        expected = Markup('<div data-snippet-id="{id}" data-weight="100" '
                          'data-campaign="foo" class="snippet-metadata">'
                          '<a href="asdf">qwer</a></div>'.format(id=snippet.id))
        self.assertEqual(snippet.render().strip(), expected)

    def test_render_no_country(self):
        """
        If the snippet isn't geolocated, don't include the data-countries
        attribute.
        """
        template = SnippetTemplateFactory.create()
        template.render = Mock()
        template.render.return_value = '<a href="asdf">qwer</a>'

        data = '{"url": "asdf", "text": "qwer"}'
        snippet = SnippetFactory.create(template=template, data=data)

        expected = Markup('<div data-snippet-id="{0}" data-weight="100" '
                          'data-campaign="" class="snippet-metadata">'
                          '<a href="asdf">qwer</a></div>'
                          .format(snippet.id))
        self.assertEqual(snippet.render().strip(), expected)

    def test_render_multiple_countries(self):
        """
        Include multiple countries in data-countries
        """
        template = SnippetTemplateFactory.create()
        template.render = Mock()
        template.render.return_value = '<a href="asdf">qwer</a>'

        data = '{"url": "asdf", "text": "qwer"}'
        snippet = SnippetFactory.create(template=template, data=data, countries=['us', 'el'])

        expected = Markup(
            '<div data-snippet-id="{0}" data-weight="100" data-campaign="" '
            'class="snippet-metadata" data-countries="el,us">'
            '<a href="asdf">qwer</a></div>'.format(snippet.id))
        self.assertEqual(snippet.render().strip(), expected)

    def test_render_exclude_search_engines(self):
        """
        If the snippet must get excluded from search engines,
        include the data-exclude-from-search-engines attribute.
        """
        template = SnippetTemplateFactory.create()
        template.render = Mock()
        template.render.return_value = '<a href="asdf">qwer</a>'

        data = '{"url": "asdf", "text": "qwer"}'
        snippet = SnippetFactory.create(template=template, data=data)
        search_providers = SearchProviderFactory.create_batch(2)
        snippet.exclude_from_search_providers.add(*search_providers)

        engines = ','.join(map(lambda x: x.identifier, search_providers))
        expected = Markup(
            '<div data-snippet-id="{id}" data-weight="100" data-campaign="" '
            'class="snippet-metadata" data-exclude-from-search-engines="{engines}">'
            '<a href="asdf">qwer</a></div>'.format(id=snippet.id, engines=engines))
        self.assertEqual(snippet.render().strip(), expected)

    def test_render_unicode(self):
        variable = SnippetTemplateVariableFactory(name='data')
        template = SnippetTemplateFactory.create(code='{{ data }}',
                                                 variable_set=[variable])
        snippet = SnippetFactory(template=template, data='{"data": "φοο"}')
        output = snippet.render()
        self.assertEqual(pq(output)[0].text, '\u03c6\u03bf\u03bf')

    def test_render_snippet_id(self):
        """Include the snippet ID in the template context when rendering."""
        snippet = SnippetFactory.create(template__code='<p>{{ snippet_id }}</p>')
        snippet.template.render = Mock()
        snippet.render()
        snippet.template.render.assert_called_with({'snippet_id': snippet.id})

    def test_render_no_snippet_id(self):
        """
        If a snippet that hasn't been saved to the database yet is
        rendered, the snippet ID should be set to 0.
        """
        snippet = SnippetFactory.build(template__code='<p>{{ snippet_id }}</p>')
        snippet.template.render = Mock()
        snippet.render()
        snippet.template.render.assert_called_with({'snippet_id': 0})

    def test_render_data_with_snippet_id(self):
        """
        Any strings included in the template context should have the
        substring "[[snippet_id]]" replaced with the ID of the snippet.
        """
        snippet = SnippetFactory.create(
            template__code='<p>{{ code }}</p>',
            data='{"code": "snippet id [[snippet_id]]", "foo": true}')
        snippet.template.render = Mock()
        snippet.render()
        snippet.template.render.assert_called_with({'code': 'snippet id {0}'.format(snippet.id),
                                                    'snippet_id': snippet.id,
                                                    'foo': True})

    @override_settings(SITE_URL='http://example.com')
    def test_get_admin_url(self):
        snippet = SnippetFactory.create()
        self.assertTrue(snippet.get_admin_url().startswith('http://example.com'))
        self.assertTrue(snippet.get_admin_url(full=False).startswith('/'))


class UploadedFileTests(TestCase):

    @override_settings(CDN_URL='http://example.com')
    def test_url_with_cdn_url(self):
        test_file = UploadedFile()
        test_file.file = Mock()
        test_file.file.url = 'foo'
        self.assertEqual(test_file.url, 'http://example.com/foo')

    @override_settings(CDN_URL='http://example.com/error/')
    def test_url_without_cdn_url(self):
        test_file = UploadedFileFactory.build()
        test_file.file = Mock()
        test_file.file.url = 'bar'
        with patch('snippets.base.models.settings', wraps=settings) as settings_mock:
            delattr(settings_mock, 'CDN_URL')
            settings_mock.SITE_URL = 'http://example.com/foo/'
            self.assertEqual(test_file.url, 'http://example.com/foo/bar')

    def test_snippets(self):
        instance = UploadedFileFactory.build()
        instance.file = MagicMock()
        instance.file.url = '/media/foo.png'
        snippets = SnippetFactory.create_batch(2, data='lalala {0} foobar'.format(instance.url))
        template = SnippetTemplateFactory.create(code='<foo>{0}</foo>'.format(instance.url))
        more_snippets = SnippetFactory.create_batch(3, template=template)
        self.assertEqual(set(instance.snippets), set(list(snippets) + list(more_snippets)))


class GenerateFilenameTests(TestCase):
    @override_settings(MEDIA_FILES_ROOT='filesroot/')
    @patch('snippets.base.models.uuid')
    def test_generate_new_filename(self, uuid_mock):
        uuid_mock.uuid4.return_value = 'bar'
        file = UploadedFileFactory.build()
        filename = _generate_filename(file, 'filename.boing')
        self.assertEqual(filename, 'filesroot/bar.boing')

    def test_generate_filename_existing_entry(self):
        obj = UploadedFileFactory.build()
        obj.file.name = 'bar.png'
        obj.save()
        filename = _generate_filename(obj, 'new_filename.boing')
        self.assertEqual(filename, 'bar.png')

    @override_settings(MEDIA_FILES_ROOT='filesroot/')
    @patch('snippets.base.models.uuid')
    def test_generate_filename_different_root(self, uuid_mock):
        uuid_mock.uuid4.return_value = 'bar'
        file = UploadedFileFactory.build()
        filename = _generate_filename(file, 'filename.boing', root='new-root')
        self.assertEqual(filename, 'new-root/bar.boing')

    def test_update_icon_new_filename(self):
        icon = IconFactory()
        filename = _generate_filename(icon, 'filename.boing', settings.MEDIA_ICONS_ROOT)
        self.assertNotEqual(icon.image.name, filename)


class TemplateTests(TestCase):
    def test_process_rendered_data(self):
        data = {
            'foo': '',
            'bar': 'bar',
        }
        expected_data = {
            'bar': 'bar',
            'links': {},
        }
        snippet = ASRSnippetFactory()
        with patch('snippets.base.models.util.fluent_link_extractor',
                   wraps=fluent_link_extractor) as fluent_link_extractor_mock:
            processed_data = snippet.template_ng._process_rendered_data(data)

        self.assertTrue(fluent_link_extractor_mock.called)
        self.assertEqual(processed_data, expected_data)

    def test_subtemplate(self):
        snippet = ASRSnippetFactory()
        subtemplate = snippet.template_relation.subtemplate
        self.assertTrue(type(subtemplate) is SimpleTemplate)

        # Test subtemplate when checking from an object that inherits Template
        subtemplate = snippet.template_relation.subtemplate.subtemplate
        self.assertTrue(type(subtemplate) is SimpleTemplate)


class IconTests(TestCase):

    @override_settings(CDN_URL='http://example.com')
    def test_url_with_cdn_url(self):
        test_file = Icon()
        test_file.image = Mock()
        test_file.image.url = 'foo'
        self.assertEqual(test_file.url, 'http://example.com/foo')

    def test_url_without_cdn_url(self):
        test_file = Icon()
        test_file.image = Mock()
        test_file.image.url = 'foo'
        with patch('snippets.base.models.settings', wraps=settings) as settings_mock:
            delattr(settings_mock, 'CDN_URL')
            settings_mock.SITE_URL = 'http://second-example.com/'
            self.assertEqual(test_file.url, 'http://second-example.com/foo')


class ASRSnippetTests(TestCase):
    def test_render(self):
        snippet = ASRSnippetFactory.create(
            template_relation__text='snippet id [[snippet_id]]',
            targets=[
                TargetFactory(jexl_expr='foo == bar'),
                TargetFactory(jexl_expr='lalo == true')
            ]
        )
        generated_result = snippet.render()
        expected_result = {
            'id': str(snippet.id),
            'template': snippet.template_ng.code_name,
            'template_version': snippet.template_ng.version,
            'campaign': snippet.campaign.slug,
            'weight': snippet.weight,
            'content': {
                'text': 'snippet id {}'.format(snippet.id),
                'links': {},
                'tall': False,
                'icon': snippet.template_ng.icon.url,
                'do_not_autoblock': False,
                'block_button_text': 'Remove this',
            },
            'targeting': 'foo == bar && lalo == true'
        }
        self.assertEqual(generated_result, expected_result)

    def test_render_preview_only(self):
        snippet = ASRSnippetFactory.create(
            template_relation__text='snippet id [[snippet_id]]',
            targets=[TargetFactory(jexl_expr='foo == bar')])
        generated_result = snippet.render(preview=True)
        expected_result = {
            'id': 'preview-{}'.format(snippet.id),
            'template': snippet.template_ng.code_name,
            'template_version': snippet.template_ng.version,
            'campaign': 'preview-{}'.format(snippet.campaign.slug),
            'weight': 100,
            'content': {
                'do_not_autoblock': True,
                'text': 'snippet id {}'.format(snippet.id),
                'links': {},
                'tall': False,
                'icon': snippet.template_ng.icon.url,
                'block_button_text': 'Remove this',
            }
        }
        self.assertEqual(generated_result, expected_result)

    @override_settings(SITE_URL='http://example.com')
    def test_get_preview_url(self):
        snippet = ASRSnippetFactory.create()
        expected_result = 'about:newtab?endpoint=http://example.com'
        expected_result += reverse('asr-preview', kwargs={'uuid': snippet.uuid})
        self.assertEqual(snippet.get_preview_url(), expected_result)

    def test_duplicate(self):
        user = UserFactory.create()
        snippet = ASRSnippetFactory.create(
            status=STATUS_CHOICES['Published'],
            locales=['en-us', 'fr'],
        )
        duplicate_snippet = snippet.duplicate(user)

        for attr in ['id', 'creator', 'created', 'modified', 'name', 'uuid']:
            self.assertNotEqual(getattr(snippet, attr), getattr(duplicate_snippet, attr))

        self.assertEqual(set(snippet.locales.all()), set(duplicate_snippet.locales.all()))
        self.assertEqual(duplicate_snippet.status, STATUS_CHOICES['Draft'])

    @override_settings(SITE_URL='http://example.com')
    def test_get_admin_url(self):
        snippet = ASRSnippetFactory.create()
        self.assertTrue(snippet.get_admin_url().startswith('http://example.com'))
        self.assertTrue(snippet.get_admin_url(full=False).startswith('/'))

    def test_channels(self):
        snippet = ASRSnippetFactory.create(
            targets=[
                TargetFactory.create(on_release=True),
                TargetFactory.create(on_beta=True, on_nightly=True),
                TargetFactory.create(on_release=False, on_esr=False,
                                     on_aurora=False, on_beta=False, on_nightly=False),
            ])

        self.assertTrue(snippet.channels, set(['release', 'beta', 'nightly']))

    def test_analytics_export(self):
        snippet = ASRSnippetFactory.create(
            name='test-snippet',
            campaign__name='test-campaign',
            category__name='test-category',
            template_relation__text=(
                'This is the <b>bold body</b> with a <a href="https://example.com">link</a>.'),
        )
        expected_data = {
            'id': snippet.id,
            'name': 'test-snippet',
            'campaign': 'test-campaign',
            'category': 'test-category',
            'url': 'https://example.com',
            'body': 'This is the bold body with a link.'
        }
        self.assertEqual(expected_data, snippet.analytics_export())
