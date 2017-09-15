import uuid
import warnings

from eth_utils import (
    is_list_like,
)

from web3.exceptions import (
    CannotHandleRequest,
    UnhandledRequest,
)
from web3.middleware import (
    combine_middlewares,
    pythonic_middleware,
    attrdict_middleware,
)

from web3.utils.compat import (
    spawn,
)
from web3.utils.datastructures import (
    NamedElementStack,
)
from web3.utils.decorators import (
    deprecated_for,
)


class RequestManager(object):
    def __init__(self, web3, providers, middlewares=None):
        self.web3 = web3
        self.pending_requests = {}

        if middlewares is None:
            middlewares = [attrdict_middleware, pythonic_middleware]

        self.middlewares = middlewares
        self.providers = providers

    web3 = None
    _providers = None

    @property
    def middlewares(self):
        return tuple(self.middleware_stack)

    @middlewares.setter
    def middlewares(self, new_middlewares):
        self.middleware_stack = NamedElementStack(new_middlewares)
        self._generate_request_functions()
        self.middleware_stack.on_change(self._generate_request_functions)

    def _generate_request_functions(self):
        self._wrapped_provider_request_functions = {
            index: combine_middlewares(
                middlewares=self.middlewares + tuple(provider.middlewares),
                web3=self.web3,
                provider_request_fn=provider.make_request,
            )
            for index, provider
            in enumerate(self.providers)
        }

    @deprecated_for("manager.middleware_stack.add(middleware [, name])")
    def add_middleware(self, middleware, name=None):
        return self.middleware_stack.add(middleware, name=name)

    @deprecated_for("manager.middleware_stack.clear()")
    def clear_middlewares(self):
        return self.middleware_stack.clear()

    @property
    def providers(self):
        return self._providers or tuple()

    @providers.setter
    def providers(self, value):
        if not is_list_like(value):
            providers = [value]
        else:
            providers = value
        self._providers = providers
        self._generate_request_functions()

    def setProvider(self, providers):
        warnings.warn(DeprecationWarning(
            "The `setProvider` API has been deprecated.  You should update your "
            "code to directly set the `manager.provider` property."
        ))
        self.providers = providers

    #
    # Provider requests and response
    #
    def _make_request(self, method, params):
        for index in range(len(self.providers)):
            make_request_fn = self._wrapped_provider_request_functions[index]
            try:
                return make_request_fn(method, params)
            except CannotHandleRequest:
                continue
        else:
            raise UnhandledRequest(
                "No providers responded to the RPC request:\n"
                "method:{0}\n"
                "params:{1}\n".format(
                    method,
                    params,
                )
            )

    def request_blocking(self, method, params):
        """
        Make a synchronous request using the provider
        """
        response = self._make_request(method, params)

        if "error" in response:
            raise ValueError(response["error"])

        return response['result']

    def request_async(self, raw_method, raw_params):
        request_id = uuid.uuid4()
        self.pending_requests[request_id] = spawn(
            self.request_blocking,
            raw_method=raw_method,
            raw_params=raw_params,
        )
        return request_id

    def receive_blocking(self, request_id, timeout=None):
        try:
            request = self.pending_requests.pop(request_id)
        except KeyError:
            raise KeyError("Request for id:{0} not found".format(request_id))
        else:
            response = request.get(timeout=timeout)

        if "error" in response:
            raise ValueError(response["error"])

        return response['result']

    def receive_async(self, request_id, *args, **kwargs):
        raise NotImplementedError("Callback pattern not implemented")
