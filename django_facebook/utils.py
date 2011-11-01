
from django.http import QueryDict
from django.conf import settings
from django.db import models
import logging
import re


logger = logging.getLogger(__name__)

def test_permissions(request, scope_list, redirect_uri=None):
    '''
    Call Facebook me/permissions to see if we are allowed to do this
    '''
    from django_facebook.api import get_persistent_graph
    from open_facebook import exceptions as facebook_exceptions
    fb = get_persistent_graph(request, redirect_uri=redirect_uri)
    permissions_dict = {}
    
    if fb:
        try:
            permissions_response = fb.get('me/permissions')
            permissions = permissions_response['data'][0]
        except facebook_exceptions.OAuthException, e:
            #this happens when someone revokes their permissions while the session
            #is still stored
            permissions = {}
        permissions_dict = dict([(k,bool(int(v))) for k,v in permissions.items() if v == '1' or v == 1])
        
    #see if we have all permissions
    scope_allowed = True
    for permission in scope_list:
        if permission not in permissions_dict:
            scope_allowed = False
            
    #raise if this happens after a redirect though
    if not scope_allowed and request.GET.get('attempt'):
        raise ValueError, 'Somehow facebook is not giving us the permissions needed, lets break instead of endless redirects. Fb was %s and permissions %s' % (fb, permissions_dict)

    return scope_allowed


def get_oauth_url(request, scope, redirect_uri=None):
    '''
    Returns the oauth url for the given request and scope
    Request maybe shouldnt be tied to this function, but for now it seems 
    rather ocnvenient
    '''
    from django_facebook import settings as facebook_settings
    scope = parse_scope(scope)
    query_dict = QueryDict('', True)
    query_dict['scope'] = ','.join(scope)
    query_dict['client_id'] = facebook_settings.FACEBOOK_APP_ID
    redirect_uri = redirect_uri or request.build_absolute_uri()

    #set attempt=1 to prevent endless redirect loops
    if 'attempt=1' not in redirect_uri:
        if '?' not in redirect_uri:
            redirect_uri += '?attempt=1'
        else:
            redirect_uri += '&attempt=1'
        
    if ('//localhost' in redirect_uri or '//127.0.0.1' in redirect_uri) and settings.DEBUG:
        raise ValueError, 'Facebook checks the domain name of your apps. Therefor you cannot run on localhost. Instead you should use something like local.fashiolista.com. Replace Fashiolista with your own domain name.'
    query_dict['redirect_uri'] = redirect_uri
    url = 'https://www.facebook.com/dialog/oauth?'
    url += query_dict.urlencode()
    return url, redirect_uri

def next_redirect(request, default='/', additional_params=None, next_key='next'):
    from django.http import HttpResponseRedirect
    if not isinstance(next_key, (list, tuple)):
        next_key = [next_key]
    
    #get the redirect url
    redirect_url = None
    for key in next_key:
        redirect_url = request.REQUEST.get(key)
        if redirect_url:
            break
    if not redirect_url:
        redirect_url = default
        
    if additional_params:
        query_params = QueryDict('', True)
        query_params.update(additional_params)
        seperator = '&' if '?' in redirect_url else '?'
        redirect_url += seperator + query_params.urlencode()
        
    return HttpResponseRedirect(redirect_url)


def get_profile_class():
    profile_string = settings.AUTH_PROFILE_MODULE
    app_label, model = profile_string.split('.')

    return models.get_model(app_label, model)
    
    
def mass_get_or_create(model_class, base_queryset, id_field, default_dict, global_defaults):
    '''
    Updates the data by inserting all not found records
    
    Doesnt delete records if not in the new data

    example usage
    >>> model_class = ListItem #the class for which you are doing the insert
    >>> base_query_set = ListItem.objects.filter(user=request.user, list=1) #query for retrieving currently stored items
    >>> id_field = 'user_id' #the id field on which to check
    >>> default_dict = {'12': dict(comment='my_new_item'), '13': dict(comment='super')} #list of default values for inserts
    >>> global_defaults = dict(user=request.user, list_id=1) #global defaults
    '''
    current_instances = list(base_queryset)
    current_ids = [unicode(getattr(c, id_field)) for c in current_instances]
    given_ids = map(unicode, default_dict.keys())
    new_ids = [g for g in given_ids if g not in current_ids]
    inserted_model_instances = []
    for new_id in new_ids:
        defaults = default_dict[new_id]
        defaults[id_field] = new_id
        defaults.update(global_defaults)
        model_instance = model_class.objects.create(
            **defaults
        )
        inserted_model_instances.append(model_instance)
        
    #returns a list of existing and new items
    return current_instances, inserted_model_instances


def get_registration_backend():
    '''
    Ensures compatability with the new and old version of django registration
    '''
    backend = None
    try:        
        #support for the newer implementation
        from registration.backends import get_backend
        try:
            backend = get_backend(settings.REGISTRATION_BACKEND)
        except:
            raise ValueError, 'Cannot get django-registration backend from settings.REGISTRATION_BACKEND'
    except ImportError, e:
        backend = None
    return backend



def parse_scope(scope):
    '''
    Turns
    'email,user_about_me'
    or
    ('email','user_about_me')
    into a nice consistent
    ['email','user_about_me']
    '''
    assert scope, 'scope is required'
    if isinstance(scope, basestring):
        scope_list = scope.split(',')
    elif isinstance(scope, (list, tuple)):
        scope_list = list(scope)
        
    return scope_list 


def to_int(input, default=0, exception=(ValueError, TypeError), regexp=None):
    '''Convert the given input to an integer or return default

    When trying to convert the exceptions given in the exception parameter
    are automatically catched and the default will be returned.

    The regexp parameter allows for a regular expression to find the digits
    in a string.
    When True it will automatically match any digit in the string.
    When a (regexp) object (has a search method) is given, that will be used.
    WHen a string is given, re.compile will be run over it first

    The last group of the regexp will be used as value
    '''
    import re
    if regexp is True:
        regexp = re.compile('(\d+)')
    elif isinstance(regexp, basestring):
        regexp = re.compile(regexp)
    elif hasattr(regexp, 'search'):
        pass
    elif regexp is not None:
        raise TypeError, 'unknown argument for regexp parameter'

    try:
        if regexp:
            match = regexp.search(input)
            if match:
                input = match.groups()[-1]
        return int(input)
    except exception:
        return default
    
def remove_query_param(url, key):
    p = re.compile('%s=[^=&]*&' % key, re.VERBOSE)
    url = p.sub('', url)
    p = re.compile('%s=[^=&]*' % key, re.VERBOSE)
    url = p.sub('', url)
    return url

def replace_query_param(url, key, value):
    p = re.compile('%s=[^=&]*' % key, re.VERBOSE)
    return p.sub('%s=%s' % (key, value), url)


DROP_QUERY_PARAMS = ['code', 'signed_request', 'state']

def cleanup_oauth_url(redirect_uri):
    '''
    We have to maintain order with respect to the queryparams which is a bit of a pain
    
    TODO: Very hacky will subclass QueryDict to SortedQueryDict at some point
    And use a decent sort function
    '''
    
    if '?' in redirect_uri:
        redirect_base, redirect_query = redirect_uri.split('?', 1)
        query_dict_items = QueryDict(redirect_query).items()
    else:
        redirect_base = redirect_uri
        query_dict_items = QueryDict('', True)

    filtered_query_items = [(k, v) for k, v in query_dict_items if k.lower() not in DROP_QUERY_PARAMS]
    #new_query_dict = QueryDict('', True)
    #new_query_dict.update(dict(filtered_query_items))
    
    excluded_query_items = [(k, v) for k, v in query_dict_items if k.lower() in DROP_QUERY_PARAMS]
    for k, v in excluded_query_items:
        redirect_uri = remove_query_param(redirect_uri, k)
    
    redirect_uri = redirect_uri.strip('?')
    redirect_uri = redirect_uri.strip('&')
    
    return redirect_uri
    
