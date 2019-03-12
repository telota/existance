from pkg_resources import resource_string


NGINX_MAPPING_PREAMBLE = """\
# This is a stub that is used to expose a particular eXist-db instance with
# the webserver to the public.
# You need to
# - include this configuration in the webserver configuration
#   - e.g. place it in /etc/nginx/proxy-mappings in conjunction with the
#     `nginx-site` template
# - replace the tokens enclosed by < and > with actual values

"""


NGINX_MAPPING_ROUTE = """\
location /<instance_name>/ {
  proxy_pass http://localhost:<instance_id>/<instance_name>/;
}

"""


NGINX_MAPPING_STATUS_FILTER = """\
# Don't make reconnaissance too easy for the bad guys.
location = /<instance_name>/status {
  allow <trusted_client>;
  deny all;
  proxy_pass http://localhost:<instance_id>/<instance_name>/status;
}
"""


TEMPLATES = {
    "existctl": resource_string(__name__, 'files/existctl.template'),
    "nginx-site": resource_string(__name__, 'files/nginx-default-site.template'),
    "nginx-mapping": NGINX_MAPPING_PREAMBLE
    + NGINX_MAPPING_ROUTE
    + NGINX_MAPPING_STATUS_FILTER,
    "systemd-unit": resource_string(__name__, 'files/existdb@.service.template'),
}
