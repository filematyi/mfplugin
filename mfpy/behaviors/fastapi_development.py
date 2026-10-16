behavior = """
For a fastapi backend implementation, follow these principles:
1. the entry point must be app.py module. That contains only the necessary details of fastapi app, middleware and
route registration. The implementation of middlewares and routes are implemented elsewhere.
2. Routes: all route implementation is stored in routes folder. Groups routes into modules logically
like user management is one module implementing all the endpoint of user management. In the routes module
the endpoint only receives the request, pass it to an imported module and return with the answer. No other
implementation allowed in a route module.
3. Schemas: all data objects used are request input, return objects, objects travaling through the application
must be implemented and stored in schemas folder. Group them logically.
4. Middlewares: All middleware implementation must be in middlewares folder, each of them has it's own module.
5. Infrastructure: all 3rd party interfaces like storages, databases, etc must have a wrapper class and must be
implemented in infrastructures folder.
6. The database schemas and all layers between raw data and the application data objects (like translation layer)
must be in database folder.
7. The logic behind each endpoint must be in services folder.
Organize them to mirror the moduel structure in routes folder.
8. if requester doesn't want something else create a basic requirements.txt file for storing dependencies.
"""
