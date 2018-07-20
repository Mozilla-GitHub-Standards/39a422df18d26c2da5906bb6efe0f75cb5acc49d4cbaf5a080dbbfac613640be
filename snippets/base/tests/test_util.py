from snippets.base.models import Snippet
from snippets.base.tests import SnippetFactory, TestCase
from snippets.base.util import first, fluent_link_extractor, get_object_or_none


class TestGetObjectOrNone(TestCase):
    def test_does_not_exist(self):
        """Return None if no matching object exists."""
        value = get_object_or_none(Snippet, name='Does not exist')
        self.assertEqual(value, None)

    def test_multiple_objects_returned(self):
        """Return None if multiple objects are returned."""
        SnippetFactory.create(data='{"multiple": 1}')
        SnippetFactory.create(data='{"multiple": 1}')
        value = get_object_or_none(Snippet, data='{"multiple": 1}')
        self.assertEqual(value, None)

    def test_exists(self):
        """If no exceptions occur, return the matched object."""
        video = SnippetFactory.create(name='exists')
        value = get_object_or_none(Snippet, name='exists')
        self.assertEqual(value, video)


class TestFirst(TestCase):
    def test_basic(self):
        items = [(0, 'foo'), (1, 'bar'), (2, 'baz')]
        self.assertEqual(first(items, lambda x: x[0] == 1), (1, 'bar'))

    def test_no_match(self):
        """Return None if the callback never passes for any item."""
        items = [(0, 'foo'), (1, 'bar'), (2, 'baz')]
        self.assertEqual(first(items, lambda x: x[0] == 17), None)


class TestFluentLinkExtractor(TestCase):
    def test_multiple_links_with_metrics(self):
        text = (
            'We have an <a href="http://example.com">example</a> and another'
            ' <a href="https://blog.mozvr.com/introducing-hubs-a-new-way-to-'
            'get-together-online/#utm_source=desktop-snippet&amp;utm_medium='
            'snippet&amp;utm_campaign=MozillaHubsIntro&amp;utm_term=8460&amp;'
            'utm_content=REL">link</a> that has more complex format. One link that has '
            'a <a data-metric="custom-click" href="https://mozilla.org">custom metric</a>'
            'and yet another that has <a foo="bar">no href attrib</a>')
        final_text = (
            'We have an <link0>example</link0> and another'
            ' <link1>link</link1> that has more complex format. One link that has '
            'a <link2>custom metric</link2>'
            'and yet another that has <link3>no href attrib</link3>')
        final_links = {
            'link0': {
                'url': 'http://example.com'
            },
            'link1': {
                'url': ('https://blog.mozvr.com/introducing-hubs-a-new-way-to-get-together-online'
                        '/#utm_source=desktop-snippet&amp;utm_medium=snippet&amp'
                        ';utm_campaign=MozillaHubsIntro&amp;utm_term=8460&amp;utm_content=REL')
            },
            'link2': {
                'url': 'https://mozilla.org',
                'metric': 'custom-click'
            },
            'link3': {
                'url': ''
            }
        }
        generated_text, generated_links = fluent_link_extractor(text)
        self.assertEqual(final_text, generated_text)
        self.assertEqual(final_links['link0'], generated_links['link0'])
        self.assertEqual(final_links['link1'], generated_links['link1'])
        self.assertEqual(final_links['link2'], generated_links['link2'])
        self.assertEqual(final_links['link3'], generated_links['link3'])
        self.assertEqual(len(generated_links), 4)
