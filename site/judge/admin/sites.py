import re
from functools import update_wrapper
from weakref import WeakSet

from django.apps import apps
from django.conf import settings
from django.contrib.admin import ModelAdmin, actions
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import ImproperlyConfigured
from django.db.models.base import ModelBase
from django.http import (
    Http404, HttpResponsePermanentRedirect, HttpResponseRedirect,
)
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from django.utils.functional import LazyObject
from django.utils.module_loading import import_string
from django.utils.text import capfirst
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.common import no_append_slash
from django.views.decorators.csrf import csrf_protect
from django.views.i18n import JavaScriptCatalog

from django.urls import include, path, re_path, reverse
from django.contrib.admin import site
from django.contrib.admin import AdminSite
from django.urls import path
from django.contrib.auth.views import LoginView
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect

from judge.views.register import RegistrationView
from judge.views import user

class CustomAdminSite(AdminSite):
    site_header = 'Custom Admin'
    site_title = 'Custom Admin Portal'
    index_title = 'Welcome to Custom Admin'

    login_template = user.CustomLoginView.as_view()

    def admin_view(self, view, cacheable=False):
        """
        Decorator to create an admin view attached to this ``AdminSite``. This
        wraps the view and provides permission checking by calling
        ``self.has_permission``.

        You'll want to use this from within ``AdminSite.get_urls()``:

            class MyAdminSite(AdminSite):

                def get_urls(self):
                    from django.urls import path

                    urls = super().get_urls()
                    urls += [
                        path('my_view/', self.admin_view(some_view))
                    ]
                    return urls

        By default, admin_views are marked non-cacheable using the
        ``never_cache`` decorator. If the view can be safely cached, set
        cacheable=True.
        """
        def inner(request, *args, **kwargs):
            if not self.has_permission(request):
                if request.path == reverse('admin:logout', current_app=self.name):
                    index_path = reverse('admin:index', current_app=self.name)
                    return HttpResponseRedirect(index_path)
                # Inner import to prevent django.contrib.admin (app) from
                # importing django.contrib.auth.models.User (unrelated model).
                return redirect('home')
            return view(request, *args, **kwargs)
        if not cacheable:
            inner = never_cache(inner)
        # We add csrf_protect here so this function can be used as a utility
        # function for any view, without having to repeat 'csrf_protect'.
        if not getattr(view, 'csrf_exempt', False):
            inner = csrf_protect(inner)
        return update_wrapper(inner, view)

    def login(self, request, extra_context=None):
        """
        Display the login form for the given HttpRequest.
        """
        if request.method == 'GET' and self.has_permission(request):
            # Already logged-in, redirect to admin index
            index_path = reverse('admin:index', current_app=self.name)
            return HttpResponseRedirect(index_path)

        # Since this module gets imported in the application's root package,
        # it cannot import models from other applications at the module level,
        # and django.contrib.admin.forms eventually imports User.
        from django.contrib.admin.forms import AdminAuthenticationForm
        from django.contrib.auth.views import LoginView
        context = {
            **self.each_context(request),
            'title': _('Log in'),
            'app_path': request.get_full_path(),
            'username': request.user.get_username(),
        }
        if (REDIRECT_FIELD_NAME not in request.GET and
                REDIRECT_FIELD_NAME not in request.POST):
            context[REDIRECT_FIELD_NAME] = reverse('admin:index', current_app=self.name)
        context.update(extra_context or {})

        defaults = {
            'extra_context': context,
            'authentication_form': self.login_form or AdminAuthenticationForm,
            'template_name': self.login_template,
        }
        request.current_app = self.name
        return LoginView.as_view(**defaults)(request)

    def autocomplete_view(self, request):
        return AutocompleteJsonView.as_view(admin_site=self)(request)

    def get_urls(self):
        from django.urls import path

        urlpatterns = super().get_urls()
    
        # Remove existing 'login' path
        updated_urlpatterns = []
        for urlpattern in urlpatterns:
            if urlpattern.name != 'login':
                updated_urlpatterns.append(urlpattern)

        updated_urlpatterns += [
            path('accounts', include([
                path('/login', self.login, name='login'),
                path('/id/find/', user.IdFindCompleteView.as_view(template_name='registration/id_find_complete.html'), name='id_find'),
                path('password/reset/', user.CustomPasswordResetView.as_view(), name='password_reset'),
                path('register/', RegistrationView.as_view(), name='registration_register'),
            ]))
        ]

        return updated_urlpatterns

custom_admin_site = CustomAdminSite(name='custom_admin')