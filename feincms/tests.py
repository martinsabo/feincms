# coding=utf-8

from datetime import datetime, timedelta
import os

from django import template
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.core import mail
from django.db import models
from django.http import Http404
from django.template import TemplateDoesNotExist
from django.template.defaultfilters import slugify
from django.test import TestCase

from feincms.content.contactform.models import ContactFormContent, ContactForm
from feincms.content.file.models import FileContent
from feincms.content.image.models import ImageContent
from feincms.content.raw.models import RawContent
from feincms.content.richtext.models import RichTextContent
from feincms.content.video.models import VideoContent

from feincms.models import Region, Template, Base
from feincms.module.blog.models import Entry
from feincms.module.medialibrary.models import Category, MediaFile
from feincms.module.page.models import Page
from feincms.templatetags import feincms_tags
from feincms.translations import short_language_code
from feincms.utils import collect_dict_values, get_object, prefill_entry_list, \
    prefilled_attribute


class Empty(object):
    """
    Helper class to use as request substitute (or whatever)
    """

    pass

class TranslationsTest(TestCase):
    def test_short_language_code(self):
        # this is quite stupid, but it's the first time I do something
        # with TestCase

        import feincms.translations
        import doctest

        doctest.testmod(feincms.translations)


class ModelsTest(TestCase):
    def test_region(self):
        # Creation should not fail

        r = Region('region', 'region title')
        t = Template('base template', 'base.html', (
            ('region', 'region title'),
            Region('region2', 'region2 title'),
            ))

        # I'm not sure whether this test tests anything at all
        self.assertEqual(r.key, t.regions[0].key)
        self.assertEqual(unicode(r), 'region title')


class UtilsTest(TestCase):
    def test_get_object(self):
        from feincms.utils import get_object

        self.assertRaises(AttributeError, lambda: get_object('feincms.does_not_exist'))
        self.assertRaises(ImportError, lambda: get_object('feincms.does_not_exist.fn'))

        self.assertEqual(get_object, get_object('feincms.utils.get_object'))

    def test_collect_dict_values(self):
        from feincms.utils import collect_dict_values

        self.assertEqual({'a': [1, 2], 'b': [3]},
            collect_dict_values([('a', 1), ('a', 2), ('b', 3)]))


class ExampleCMSBase(Base):
    pass

ExampleCMSBase.register_regions(('region', 'region title'))

class CMSBaseTest(TestCase):
    def test_01_simple_content_type_creation(self):
        ExampleCMSBase.create_content_type(ContactFormContent)
        ExampleCMSBase.create_content_type(FileContent)
        ExampleCMSBase.create_content_type(ImageContent,
            POSITION_CHOICES=(('left', 'left'),))
        ExampleCMSBase.create_content_type(RawContent)
        ExampleCMSBase.create_content_type(RichTextContent)
        ExampleCMSBase.create_content_type(VideoContent)

    def test_02_rsscontent_creation(self):
        # this test resides in its own method because the required feedparser
        # module is not available everywhere
        from feincms.content.rss.models import RSSContent
        ExampleCMSBase.create_content_type(RSSContent)

    def test_03_double_creation(self):
        # creating a content type twice is forbidden
        self.assertRaises(ImproperlyConfigured,
            lambda: ExampleCMSBase.create_content_type(RawContent))

    def test_04_mediafilecontent_creation(self):
        # the medialibrary needs to be enabled, otherwise this test fails

        from feincms.content.medialibrary.models import MediaFileContent

        # We use the convenience method here which has defaults for
        # POSITION_CHOICES
        MediaFileContent.default_create_content_type(ExampleCMSBase)

    def test_05_non_abstract_content_type(self):
        # Should not be able to create a content type from a non-abstract base type
        class TestContentType(models.Model):
            pass

        self.assertRaises(ImproperlyConfigured,
            lambda: ExampleCMSBase.create_content_type(TestContentType))

    def test_06_videocontent(self):
        type = ExampleCMSBase.content_type_for(VideoContent)
        obj = type()
        obj.video = 'http://www.youtube.com/watch?v=zmj1rpzDRZ0'

        assert 'x-shockwave-flash' in obj.render()


Page.register_extensions('datepublisher', 'navigation', 'seo', 'symlinks',
                         'titles', 'translations', 'seo')
Page.create_content_type(ContactFormContent, form=ContactForm)


class PagesTestCase(TestCase):
    def setUp(self):
        u = User(username='test', is_active=True, is_staff=True, is_superuser=True)
        u.set_password('test')
        u.save()

        Page.register_templates({
                'key': 'base',
                'title': 'Standard template',
                'path': 'feincms_base.html',
                'regions': (
                    ('main', 'Main content area'),
                    ('sidebar', 'Sidebar', 'inherited'),
                    ),
                }, {
                'key': 'theother',
                'title': 'This actually exists',
                'path': 'base.html',
                'regions': (
                    ('main', 'Main content area'),
                    ('sidebar', 'Sidebar', 'inherited'),
                    ),
                })

    def login(self):
        assert self.client.login(username='test', password='test')

    def create_page(self, title='Test page', parent='', **kwargs):
        dic = {
            'title': title,
            'slug': kwargs.get('slug', slugify(title)),
            'parent': parent,
            'template_key': 'base',
            'publication_date_0': '2009-01-01',
            'publication_date_1': '00:00:00',
            'initial-publication_date_0': '2009-01-01',
            'initial-publication_date_1': '00:00:00',
            'language': 'en',
            }
        dic.update(kwargs)
        return self.client.post('/admin/page/page/add/', dic)

    def create_default_page_set(self):
        self.login()
        self.create_page()
        return self.create_page('Test child page', 1)

    def test_01_tree_editor(self):
        self.login()
        assert self.client.get('/admin/page/page/').status_code == 200

    def test_02_add_page(self):
        self.login()
        self.assertRedirects(self.create_page(title='Test page ' * 10, slug='test-page'),
                             '/admin/page/page/')
        assert Page.objects.count() == 1
        self.assertContains(self.client.get('/admin/page/page/'), '…')

    def test_03_item_editor(self):
        self.login()
        self.assertRedirects(self.create_page(_continue=1), '/admin/page/page/1/')
        assert self.client.get('/admin/page/page/1/').status_code == 200

    def test_03_add_another(self):
        self.login()
        self.assertRedirects(self.create_page(_addanother=1), '/admin/page/page/add/')

    def test_04_add_child(self):
        response = self.create_default_page_set()
        self.assertRedirects(response, '/admin/page/page/')
        assert Page.objects.count() == 2

        page = Page.objects.get(pk=2)
        self.assertEqual(page.get_absolute_url(), '/test-page/test-child-page/')

    def test_05_override_url(self):
        self.create_default_page_set()

        page = Page.objects.get(pk=1)
        page.override_url = '/something/'
        page.save()

        page2 = Page.objects.get(pk=2)
        self.assertEqual(page2.get_absolute_url(), '/something/test-child-page/')

        page.override_url = '/'
        page.save()
        page2 = Page.objects.get(pk=2)
        self.assertEqual(page2.get_absolute_url(), '/test-child-page/')

    def test_06_tree_editor_save(self):
        self.create_default_page_set()

        self.client.post('/admin/page/page/', {
            '__cmd': 'save_tree',
            'tree': '[[2, 0, 1], [1, 2, 0]]',
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        page = Page.objects.get(pk=1)
        self.assertEqual(page.get_absolute_url(), '/test-child-page/test-page/')

    def test_07_tree_editor_delete(self):
        self.create_default_page_set()

        self.client.post('/admin/page/page/', {
            '__cmd': 'delete_item',
            'item_id': 2,
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertRaises(Page.DoesNotExist, lambda: Page.objects.get(pk=2))

    def test_07_tree_editor_invalid_ajax(self):
        self.login()
        self.assertContains(self.client.post('/admin/page/page/', {
            '__cmd': 'notexists',
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest'),
            'Oops. AJAX request not understood.')

    def is_published(self, url, should_be=True):
        try:
            self.client.get(url)
        except TemplateDoesNotExist, e:
            if should_be:
                if e.args != ('feincms_base.html',):
                    raise
            else:
                if e.args != ('404.html',):
                    raise

    def test_08_publishing(self):
        self.create_default_page_set()

        page = Page.objects.get(pk=1)
        self.is_published(page.get_absolute_url(), should_be=False)

        page.active = True
        page.save()
        self.is_published(page.get_absolute_url(), should_be=True)

        old_publication = page.publication_date
        page.publication_date = datetime.now() + timedelta(days=1)
        page.save()
        self.is_published(page.get_absolute_url(), should_be=False)

        page.publication_date = old_publication
        page.publication_end_date = datetime.now() - timedelta(days=1)
        page.save()
        self.is_published(page.get_absolute_url(), should_be=False)

        page.publication_end_date = datetime.now() + timedelta(days=1)
        page.save()
        self.is_published(page.get_absolute_url(), should_be=True)

    def create_pagecontent(self, page):
         return self.client.post('/admin/page/page/1/', {
            'title': page.title,
            'slug': page.slug,
            #'parent': page.parent_id, # this field is excluded from the form
            'template_key': page.template_key,
            'publication_date_0': '2009-01-01',
            'publication_date_1': '00:00:00',
            'initial-publication_date_0': '2009-01-01',
            'initial-publication_date_1': '00:00:00',
            'language': 'en',

            'rawcontent-TOTAL_FORMS': 1,
            'rawcontent-INITIAL_FORMS': 0,

            'rawcontent-0-parent': 1,
            'rawcontent-0-region': 'main',
            'rawcontent-0-ordering': 0,
            'rawcontent-0-text': 'This is some example content',

            'mediafilecontent-TOTAL_FORMS': 1,
            'mediafilecontent-INITIAL_FORMS': 0,

            'mediafilecontent-0-parent': 1,
            'mediafilecontent-0-position': 'block',

            'imagecontent-TOTAL_FORMS': 1,
            'imagecontent-INITIAL_FORMS': 0,

            'imagecontent-0-parent': 1,
            'imagecontent-0-position': 'default',

            'contactformcontent-TOTAL_FORMS': 1,
            'contactformcontent-INITIAL_FORMS': 0,
            })

    def test_09_pagecontent(self):
        self.create_default_page_set()

        page = Page.objects.get(pk=1)
        response = self.create_pagecontent(page)
        self.assertRedirects(response, '/admin/page/page/')
        self.assertEqual(page.content.main[0].__class__.__name__, 'RawContent')

        page2 = Page.objects.get(pk=2)
        page2.symlinked_page = page
        self.assertEqual(page2.content.main[0].__class__.__name__, 'RawContent')

        self.assertEqual(len(page2.content.main), 1)
        self.assertEqual(len(page2.content.sidebar), 0)
        self.assertEqual(len(page2.content.nonexistant_region), 0)

    def test_10_mediafile_and_imagecontent(self):
        self.create_default_page_set()

        page = Page.objects.get(pk=1)
        self.create_pagecontent(page)

        path = os.path.join(settings.MEDIA_ROOT, 'somefile.jpg')
        f = open(path, 'wb')
        f.write('blabla')
        f.close()

        category = Category.objects.create(title='Category', parent=None)
        category2 = Category.objects.create(title='Something', parent=category)

        self.assertEqual(unicode(category2), 'Category - Something')
        self.assertEqual(unicode(category), 'Category')

        mediafile = MediaFile.objects.create(file='somefile.jpg')
        mediafile.categories = [category]
        page.mediafilecontent_set.create(
            mediafile=mediafile,
            region='main',
            position='block',
            ordering=1)

        self.assertContains(self.client.get('/admin/page/page/1/'), 'no caption')

        mediafile.translations.create(caption='something',
            language_code='%s-ha' % short_language_code())

        mf = page.content.main[1].mediafile

        self.assertEqual(mf.translation.caption, 'something')
        self.assertEqual(mf.translation.short_language_code(), short_language_code())
        self.assertNotEqual(mf.get_absolute_url(), '')
        self.assertEqual(unicode(mf), 'something (somefile.jpg / 6 bytes)')
        self.assertEqual(mf.file_type(), 'Image')

        os.unlink(path)

        self.client.get('/admin/page/page/1/')

        assert 'alt="something"' in page.content.main[1].render()

        page.imagecontent_set.create(image='somefile.jpg', region='main', position='default', ordering=2)

        assert 'somefile.jpg' in page.content.main[2].render()

    def test_11_translations(self):
        self.create_default_page_set()

        page1 = Page.objects.get(pk=1)
        self.assertEqual(len(page1.available_translations()), 0)

        page1 = Page.objects.get(pk=1)
        page2 = Page.objects.get(pk=2)

        page2.language = 'de'
        page2.translation_of = page1
        page2.save()

        self.assertEqual(len(page2.available_translations()), 1)
        self.assertEqual(len(page1.available_translations()), 1)

    def test_12_titles(self):
        self.create_default_page_set()

        page = Page.objects.get(pk=1)

        self.assertEqual(page.page_title, page.title)
        self.assertEqual(page.content_title, page.title)

        page._content_title = 'Something\nawful'
        page._page_title = 'Hello world'
        page.save()

        self.assertEqual(page.page_title, 'Hello world')
        self.assertEqual(page.content_title, 'Something')
        self.assertEqual(page.content_subtitle, 'awful')

        page._content_title = 'Only one line'
        self.assertEqual(page.content_title, 'Only one line')
        self.assertEqual(page.content_subtitle, '')

        page._content_title = ''
        self.assertEqual(page.content_title, page.title)
        self.assertEqual(page.content_subtitle, '')

    def test_13_inheritance(self):
        self.create_default_page_set()

        page = Page.objects.get(pk=1)
        page.rawcontent_set.create(
            region='sidebar',
            ordering=0,
            text='Something')

        page2 = Page.objects.get(pk=2)

        self.assertEqual(page2.content.sidebar[0].render(), 'Something')

    def test_14_richtext(self):
        # only create the content type to test the item editor
        # customization hooks
        tmp = Page._feincms_content_types[:]
        type = Page.create_content_type(RichTextContent, regions=('notexists',))
        Page._feincms_content_types = tmp

        from django.utils.safestring import SafeData
        obj = type()
        obj.text = 'Something'
        assert isinstance(obj.render(), SafeData)

    def test_15_frontend_editing(self):
        self.create_default_page_set()
        page = Page.objects.get(pk=1)
        self.create_pagecontent(page)

        assert self.client.get('/admin/page/page/1/rawcontent/1/').status_code == 200
        assert self.client.post('/admin/page/page/1/rawcontent/1/', {
            'rawcontent-text': 'blablabla',
            }).status_code == 200

        self.assertEqual(page.content.main[0].render(), 'blablabla')
        self.assertEqual(feincms_tags.feincms_frontend_editing(page, {}), u'')

        request = Empty()
        request.session = {'frontend_editing': True}

        assert 'class="fe_box"' in\
            page.content.main[0].fe_render(request=request)

    def test_16_template_tags(self):
        self.create_default_page_set()
        page = Page.objects.get(pk=1)
        self.create_pagecontent(page)

        self.assertEqual(feincms_tags.feincms_render_region(page, 'main', {}),
                         'This is some example content')
        self.assertEqual(feincms_tags.feincms_render_content(page.content.main[0], {}),
                         'This is some example content')

    def test_17_page_template_tags(self):
        self.create_default_page_set()

        page1 = Page.objects.get(pk=1)
        page2 = Page.objects.get(pk=2)
        ctx = template.Context({'feincms_page': page2})

        page2.language = 'de'
        page2.translation_of = page1
        page2.active = True
        page2.in_navigation = True
        page2.save()

        t = template.Template('{% load feincms_page_tags %}{% feincms_parentlink of feincms_page level=1 %}')
        self.assertEqual(t.render(ctx), '/test-page/')

        t = template.Template('{% load feincms_page_tags %}{% feincms_languagelinks for feincms_page as links %}{% for key, name, link in links %}{{ key }}:{{ link }}{% if not forloop.last %},{% endif %}{% endfor %}')
        self.assertEqual(t.render(ctx), 'en:/test-page/,de:/test-page/test-child-page/')

        t = template.Template('{% load feincms_page_tags %}{% feincms_navigation of feincms_page as nav level=1 %}{% for p in nav %}{{ p.get_absolute_url }}{% if not forloop.last %},{% endif %}{% endfor %}')
        self.assertEqual(t.render(ctx), '')

        # XXX should the other template tags not respect the in_navigation setting too?
        page1.active = True
        page1.in_navigation = True
        page1.save()

        self.assertEqual(t.render(ctx), '/test-page/')

        t = template.Template('{% load feincms_page_tags %}{% feincms_navigation of feincms_page as nav level=2 %}{% for p in nav %}{{ p.get_absolute_url }}{% if not forloop.last %},{% endif %}{% endfor %}')
        self.assertEqual(t.render(ctx), '/test-page/test-child-page/')

        t = template.Template('{% load feincms_page_tags %}{% feincms_navigation of feincms_page as nav level=99 %}{% for p in nav %}{{ p.get_absolute_url }}{% if not forloop.last %},{% endif %}{% endfor %}')
        self.assertEqual(t.render(ctx), '')

        t = template.Template('{% load feincms_page_tags %}{% feincms_breadcrumbs feincms_page %}')
        self.assertEqual(t.render(ctx), u'<a href="/test-page/">Test page</a> &gt; Test child page')

    def test_18_default_render_method(self):
        """
        Test the default render() behavior of selecting render_<region> methods
        to do the (not so) heavy lifting.
        """

        class Something(models.Model):
            class Meta:
                abstract = True

            def render_main(self):
                return u'Hello'

        # do not register this model in the internal FeinCMS bookkeeping structures
        tmp = Page._feincms_content_types[:]
        type = Page.create_content_type(Something, regions=('notexists',))
        Page._feincms_content_types = tmp

        s = type(region='main', ordering='1')

        self.assertEqual(s.render(), 'Hello')

    def test_19_page_manager(self):
        self.create_default_page_set()

        page = Page.objects.get(pk=2)
        page.active = True
        page.save()

        self.assertEqual(page, Page.objects.page_for_path(page.get_absolute_url()))
        self.assertEqual(page, Page.objects.best_match_for_path(page.get_absolute_url() + 'something/hello/'))

        self.assertRaises(Http404, lambda: Page.objects.best_match_for_path('/blabla/blabla/', raise404=True))

    def test_20_redirects(self):
        self.create_default_page_set()
        page1 = Page.objects.get(pk=1)
        page2 = Page.objects.get(pk=2)

        page2.active = True
        page2.publication_date = datetime.now() - timedelta(days=1)
        page2.override_url = '/blablabla/'
        page2.redirect_to = page1.get_absolute_url()
        page2.save()

        # regenerate cached URLs in the whole tree
        page1.active = True
        page1.save()

        page2 = Page.objects.get(pk=2)

        # page2 has been modified too, but its URL should not have changed
        try:
            self.assertRedirects(self.client.get('/blablabla/'), page1.get_absolute_url())
        except TemplateDoesNotExist, e:
            # catch the error from rendering page1
            if e.args != ('feincms_base.html',):
                raise

    def test_21_copy_content(self):
        self.create_default_page_set()
        page = Page.objects.get(pk=1)
        self.create_pagecontent(page)

        page2 = Page.objects.get(pk=2)
        page2.copy_content_from(page)
        self.assertEqual(len(page2.content.main), 1)

    def test_22_contactform(self):
        self.create_default_page_set()
        page = Page.objects.get(pk=1)
        page.active = True
        page.template_key = 'theother'
        page.save()

        page.contactformcontent_set.create(email='mail@example.com', subject='bla',
                                           region='main', ordering=0)

        request = Empty()
        request.method = 'GET'
        assert 'form' in page.content.main[0].render(request=request)

        self.client.post(page.get_absolute_url(), {
            'name': 'So what\'s your name, dude?',
            'email': 'another@example.com',
            'subject': 'This is a test. Please calm down',
            'content': 'Hell on earth.',
            })

        self.assertEquals(len(mail.outbox), 1)
        self.assertEquals(mail.outbox[0].subject, 'This is a test. Please calm down')


Entry.register_extensions('seo', 'translations', 'seo')
class BlogTestCase(TestCase):
    def setUp(self):
        u = User(username='test', is_active=True, is_staff=True, is_superuser=True)
        u.set_password('test')
        u.save()

        Entry.register_regions(('main', 'Main region'))
        Entry.prefilled_categories = prefilled_attribute('categories')
        Entry.prefilled_rawcontent_set = prefilled_attribute('rawcontent_set')

    def login(self):
        assert self.client.login(username='test', password='test')

    def create_entry(self):
        entry = Entry.objects.create(
            published=True,
            title='Something',
            slug='something',
            language='en')

        entry.rawcontent_set.create(
            region='main',
            ordering=0,
            text='Something awful')

        return entry

    def create_entries(self):
        entry = self.create_entry()

        Entry.objects.create(
            published=True,
            title='Something 2',
            slug='something-2',
            language='de',
            translation_of=entry)

        Entry.objects.create(
            published=True,
            title='Something 3',
            slug='something-3',
            language='de')

    def test_01_prefilled_attributes(self):
        self.create_entry()

        objects = prefill_entry_list(Entry.objects.published(), 'rawcontent_set', 'categories')

        self.assertEqual(len(objects[0].prefilled_categories), 0)
        self.assertEqual(len(objects[0].prefilled_rawcontent_set), 1)
        self.assertEqual(unicode(objects[0]), 'Something')

        self.login()
        assert self.client.get('/admin/blog/entry/').status_code == 200
        assert self.client.get('/admin/blog/entry/1/').status_code == 200

    def test_02_translations(self):
        self.create_entries()

        entries = Entry.objects.in_bulk((1, 2, 3))

        self.assertEqual(len(entries[1].available_translations()), 1)
        self.assertEqual(len(entries[2].available_translations()), 1)
        self.assertEqual(len(entries[3].available_translations()), 0)
