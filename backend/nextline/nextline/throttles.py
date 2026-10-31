"""Per-IP limits on account endpoints, the main target for bots (mass sign-ups, password guessing).

Counts live in the shared database cache (see CACHES), so every server process sees the same numbers.
Rates are set in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].
"""
from rest_framework.throttling import SimpleRateThrottle

# POST endpoints that create accounts or log in. Token refresh is left out: the app calls it every 15 minutes.
AUTH_PATHS = (
    '/api/auth/users/',
    '/api/auth/jwt/create/',
    '/api/user/change-password/',
)
SIGNUP_PATH = '/api/auth/users/'


class _PostToPathsThrottle(SimpleRateThrottle):
    paths = ()
    exact = False

    def get_cache_key(self, request, view):
        if request.method != 'POST':
            return None
        path = request.path
        matches = path in self.paths if self.exact else any(path.startswith(p) for p in self.paths)
        if not matches:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class AuthThrottle(_PostToPathsThrottle):
    """Log-ins, sign-ups and password changes, per IP address."""
    scope = 'auth'
    paths = AUTH_PATHS


class SignupThrottle(_PostToPathsThrottle):
    """New accounts per IP address."""
    scope = 'signup'
    paths = (SIGNUP_PATH,)
    exact = True
