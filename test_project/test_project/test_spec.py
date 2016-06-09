import unittest
import transaction
import testing.postgresql
import webtest
from pyramid.paster import get_app
from sqlalchemy import create_engine

from .models import (
    DBSession,
    Base
)

from . import test_data

class TestSpec(unittest.TestCase):
    '''Test compliance against jsonapi spec.

    http://jsonapi.org/format/
    '''

    @classmethod
    def setUpClass(cls):
        '''Create a test DB and import data.'''
        # Create a new database somewhere in /tmp
        cls.postgresql = testing.postgresql.Postgresql(port=7654)
        cls.engine = create_engine(cls.postgresql.url())
        DBSession.configure(bind=cls.engine)

        cls.app = get_app('testing.ini')
        cls.test_app = webtest.TestApp(cls.app)

    @classmethod
    def tearDownClass(cls):
        '''Throw away test DB.'''
        DBSession.close()
        cls.postgresql.stop()

    def setUp(self):
        Base.metadata.create_all(self.engine)
        # Add some basic test data.
        test_data.add_to_db()
        transaction.begin()

    def tearDown(self):
        transaction.abort()
        Base.metadata.drop_all(self.engine)

    def test_spec_server_content_type(self):
        '''Response should have correct content type.

        Servers MUST send all JSON API data in response documents with the
        header Content-Type: application/vnd.api+json without any media type
        parameters.
        '''
        # Fetch a representative page
        r = self.test_app.get('/people')
        self.assertEqual(r.content_type, 'application/vnd.api+json')

    def test_spec_incorrect_client_content_type(self):
        '''Server should return error if we send media type parameters.

        Servers MUST respond with a 415 Unsupported Media Type status code if a
        request specifies the header Content-Type: application/vnd.api+json with
        any media type parameters.
        '''
        r = self.test_app.get(
            '/people',
            headers={ 'Content-Type': 'application/vnd.api+json; param=val' },
            status=415,
        )

    def test_spec_accept_not_acceptable(self):
        '''Server should respond with 406 if all jsonapi media types have parameters.

        Servers MUST respond with a 406 Not Acceptable status code if a
        request’s Accept header contains the JSON API media type and all
        instances of that media type are modified with media type parameters.
        '''
        # Should work with correct accepts header.
        r = self.test_app.get(
            '/people',
            headers={ 'Accept': 'application/vnd.api+json' },
        )
        # 406 with one incorrect type.
        r = self.test_app.get(
            '/people',
            headers={ 'Accept': 'application/vnd.api+json; param=val' },
            status=406,
        )
        # 406 with more than one type but none without params.
        r = self.test_app.get(
            '/people',
            headers={ 'Accept': 'application/vnd.api+json; param=val,' +
                'application/vnd.api+json; param2=val2' },
            status=406,
        )

    def test_spec_toplevel_must(self):
        '''Server response must have one of data, errors or meta.

        A JSON object MUST be at the root of every JSON API request and response
        containing data.

        A document MUST contain at least one of the following top-level members:

            * data: the document’s “primary data”
            * errors: an array of error objects
            * meta: a meta object that contains non-standard meta-information.
        '''
        # Should be object with data member.
        r = self.test_app.get('/people')
        self.assertIn('data', r.json)
        # Should also have a meta member.
        self.assertIn('meta', r.json)

        # Should be object with an array of errors.
        r = self.test_app.get(
            '/people',
            headers={ 'Content-Type': 'application/vnd.api+json; param=val' },
            status=415,
        )
        self.assertIn('errors', r.json)
        self.assertIsInstance(r.json['errors'], list)

    def test_spec_get_primary_data_empty(self):
        '''Should return an empty list of results.

        Primary data MUST be either:

            * ...or an empty array ([])

        A logical collection of resources MUST be represented as an array, even
        if it... is empty.
        '''
        r = self.test_app.get('/people?filter[name:eq]=doesnotexist')
        self.assertEqual(len(r.json['data']), 0)

    def test_spec_get_primary_data_array(self):
        '''Should return an array of resource objects.

        Primary data MUST be either:

            * an array of resource objects, an array of resource identifier
            objects, or an empty array ([]), for requests that target resource
            collections
        '''
        # Data should be an array of person resource objects or identifiers.
        r = self.test_app.get('/people')
        self.assertIn('data', r.json)
        self.assertIsInstance(r.json['data'], list)
        item = r.json['data'][0]


    def test_spec_get_primary_data_array_of_one(self):
        '''Should return an array of one resource object.

        A logical collection of resources MUST be represented as an array, even
        if it only contains one item...
        '''
        r = self.test_app.get('/people?page[limit]=1')
        self.assertIn('data', r.json)
        self.assertIsInstance(r.json['data'], list)
        self.assertEqual(len(r.json['data']), 1)

    def test_spec_get_primary_data_single(self):
        '''Should return a single resource object.

        Primary data MUST be either:

            * a single resource object, a single resource identifier object, or
            null, for requests that target single resources
        '''
        # Find the id of alice.
        r = self.test_app.get('/people?filter[name:eq]=alice')
        item = r.json['data'][0]
        self.assertEqual(item['attributes']['name'], 'alice')
        alice_id = item['id']
        # Now get alice object.
        r = self.test_app.get('/people/' + alice_id)
        alice = r.json['data']
        self.assertEqual(alice['attributes']['name'], 'alice')

    def test_spec_resource_object_must(self):
        '''Resource object should have at least id and type.

        A resource object MUST contain at least the following top-level members:
            * id
            * type

        The values of the id and type members MUST be strings.
        '''
        r = self.test_app.get('/people?page[limit]=1')
        item = r.json['data'][0]
        # item must have at least a type and id.
        self.assertEqual(item['type'], 'people')
        self.assertIn('id', item)
        self.assertIsInstance(item['type'], str)
        self.assertIsInstance(item['id'], str)

    def test_spec_resource_object_must(self):
        '''Fetched resource should have attributes, relationships, links, meta.

        a resource object MAY contain any of these top-level members:

            * attributes: an attributes object representing some of the
              resource’s data.

            * relationships: a relationships object describing relationships
              between the resource and other JSON API resources.

            * links: a links object containing links related to the resource.

            * meta: a meta object containing non-standard meta-information about
              a resource that can not be represented as an attribute or
              relationship.
        '''
        r = self.test_app.get('/people?page[limit]=1')
        item = r.json['data'][0]
        self.assertIn('attributes', item)
        #self.assertIn('relationships', item)
        self.assertIn('links', item)
        #self.assertIn('meta', item)

    def test_spec_type_id_identify_resource(self):
        '''Using type and id should fetch a single resource.

        Within a given API, each resource object’s type and id pair MUST
        identify a single, unique resource.
        '''
        # Find the id of alice.
        r = self.test_app.get('/people?filter[name:eq]=alice')
        item = r.json['data'][0]
        self.assertEqual(item['attributes']['name'], 'alice')
        alice_id = item['id']

        # Search for alice by id. We should get one result whose name is alice.
        r = self.test_app.get('/people?filter[id:eq]={}'.format(alice_id))
        self.assertEqual(len(r.json['data']), 1)
        item = r.json['data'][0]
        self.assertEqual(item['id'], alice_id)
        self.assertEqual(item['attributes']['name'], 'alice')

    def test_spec_attributes(self):
        '''attributes key should be an object.

        The value of the attributes key MUST be an object (an “attributes
        object”). Members of the attributes object (“attributes”) represent
        information about the resource object in which it’s defined.
        '''
        # Fetch a single post.
        r = self.test_app.get('/posts?page[limit]=1')
        item = r.json['data'][0]
        # Check attributes.
        self.assertIn('attributes', item)
        atts = item['attributes']
        self.assertIn('title', atts)
        self.assertIn('content', atts)
        self.assertIn('published_at', atts)

    def test_spec_no_foreign_keys(self):
        '''No forreign keys in attributes.

        Although has-one foreign keys (e.g. author_id) are often stored
        internally alongside other information to be represented in a resource
        object, these keys SHOULD NOT appear as attributes.
        '''
        # posts have author_id and blog_id as has-one forreign keys. Check that
        # they don't make it into the JSON representation (they should be in
        # relationships instead).

        # Fetch a single post.
        r = self.test_app.get('/posts?page[limit]=1')
        item = r.json['data'][0]
        # Check for forreign keys.
        self.assertNotIn('author_id', item['attributes'])
        self.assertNotIn('blog_id', item['attributes'])

    def test_spec_relationships_object(self):
        '''Relationships key should be object.

        The value of the relationships key MUST be an object (a “relationships
        object”). Members of the relationships object (“relationships”)
        represent references from the resource object in which it’s defined to
        other resource objects.
        '''
        # Fetch a single blog (has to-one and to-many realtionships)
        r = self.test_app.get('/blogs?page[limit]=1')
        item = r.json['data'][0]
        # Should have relationships key
        self.assertIn('relationships', item)
        rels = item['relationships']

        # owner: to-one
        self.assertIn('owner', rels)
        owner = rels['owner']
        self.assertIn('links', owner)
        self.assertIn('data', owner)
        self.assertIsInstance(owner['data'], dict)
        self.assertIn('type', owner['data'])
        self.assertIn('id', owner['data'])

        # posts: to-many
        self.assertIn('posts', rels)
        posts = rels['posts']
        self.assertIn('links', posts)
        self.assertIn('data', posts)
        self.assertIsInstance(posts['data'], list)
        self.assertIn('type', posts['data'][0])
        self.assertIn('id', posts['data'][0])

    def test_spec_relationships_links(self):
        '''Relationships links object should have 'self' and 'related' links.
        '''
        # Fetch a single blog (has to-one and to-many relationships)
        r = self.test_app.get('/blogs?page[limit]=1')
        item = r.json['data'][0]
        # Should have relationships key
        links = item['relationships']['owner']['links']
        self.assertIn('self', links)
        self.assertTrue(
            links['self'].endswith(
                '/blogs/{}/relationships/owner'.format(item['id'])
            )
        )
        self.assertIn('related', links)
        self.assertTrue(
            links['related'].endswith(
                '/blogs/{}/owner'.format(item['id'])
            )
        )

    def test_spec_related_get(self):
        ''''related' link should fetch related resource(s).

        If present, a related resource link MUST reference a valid URL, even if
        the relationship isn’t currently associated with any target resources.
        '''
        # Fetch a single blog (has to-one and to-many relationships)
        r = self.test_app.get('/blogs/1')
        item = r.json['data']
        owner_url = item['relationships']['owner']['links']['related']
        posts_url = item['relationships']['posts']['links']['related']

        owner_data = self.test_app.get(owner_url).json['data']
        # owner should be a single object.
        self.assertIsInstance(owner_data, dict)
        # owner should be of type 'people'
        self.assertEqual(owner_data['type'], 'people')

        posts_data = self.test_app.get(posts_url).json['data']
        # posts should be a collection.
        self.assertIsInstance(posts_data, list)
        # each post should be of type 'posts'
        for post in posts_data:
            self.assertEqual(post['type'], 'posts')

    def test_spec_resource_linkage(self):
        '''Appropriate related resource identifiers in relationship.

        Resource linkage in a compound document allows a client to link together
        all of the included resource objects without having to GET any URLs via
        links.

        Resource linkage MUST be represented as one of the following:

            * null for empty to-one relationships.
            * an empty array ([]) for empty to-many relationships.
            * a single resource identifier object for non-empty to-one
             relationships.
            * an array of resource identifier objects for non-empty to-many
             relationships.
        '''
        # An anonymous comment.
        # 'null for empty to-one relationships.'
        comment = self.test_app.get('/comments/5').json['data']
        self.assertIsNone(comment['relationships']['author']['data'])

        # A comment with an author.
        # 'a single resource identifier object for non-empty to-one
        # relationships.'
        comment = self.test_app.get('/comments/1').json['data']
        author = comment['relationships']['author']['data']
        self.assertEqual(author['type'], 'people')

        # A post with no comments.
        # 'an empty array ([]) for empty to-many relationships.'
        post = self.test_app.get('/posts/1').json['data']
        comments = post['relationships']['comments']['data']
        self.assertEqual(len(comments), 0)

        # A post with comments.
        # 'an array of resource identifier objects for non-empty to-many
        # relationships.'
        post = self.test_app.get('/posts/4').json['data']
        comments = post['relationships']['comments']['data']
        self.assertGreater(len(comments), 0)
        self.assertEqual(comments[0]['type'], 'comments')

    def test_spec_links_self(self):
        ''''self' link should fetch same object.

        The optional links member within each resource object contains links
        related to the resource.

        If present, this links object MAY contain a self link that identifies
        the resource represented by the resource object.

        A server MUST respond to a GET request to the specified URL with a
        response that includes the resource as the primary data.
        '''
        person = self.test_app.get('/people/1').json['data']
        # Make sure we got the expected person.
        self.assertEqual(person['type'], 'people')
        self.assertEqual(person['id'], '1')
        # Now fetch the self link.
        person_again = self.test_app.get(person['links']['self']).json['data']
        # Make sure we got the same person.
        self.assertEqual(person_again['type'], 'people')
        self.assertEqual(person_again['id'], '1')

    def test_spec_included_array(self):
        '''Included resources should be in an array under 'included' member.

        In a compound document, all included resources MUST be represented as an
        array of resource objects in a top-level included member.
        '''
        person = self.test_app.get('/people/1?include=blogs').json
        self.assertIsInstance(person['included'], list)
        # Each item in the list should be a resource object: we'll look for
        # type, id and attributes.
        for blog in person['included']:
            self.assertIn('id', blog)
            self.assertEqual(blog['type'], 'blogs')
            self.assertIn('attributes', blog)

    def test_spec_bad_include(self):
        '''Should 400 error on attempt to fetch non existent relationship path.

        If a server is unable to identify a relationship path or does not
        support inclusion of resources from a path, it MUST respond with 400 Bad
        Request.
        '''
        # Try to include a relationship that doesn't exist.
        r = self.test_app.get('/people/1?include=frogs', status=400)

    def test_spec_nested_include(self):
        '''Should return includes for nested resources.

        In order to request resources related to other resources, a
        dot-separated path for each relationship name can be specified:

            * GET /articles/1?include=comments.author
        '''
        r = self.test_app.get('/people/1?include=comments.author')
        people_seen = set()
        types_expected = {'people', 'comments'}
        types_seen = set()
        for item in r.json['included']:
            # Shouldn't see any types other than comments and people.
            self.assertIn(item['type'], types_expected)
            types_seen.add(item['type'])

            # We should only see people 1, and only once.
            if item['type'] == 'people':
                self.assertNotIn(item['id'], people_seen)
                people_seen.add(item['id'])

        # We should have seen at least one of each type.
        self.assertIn('people', types_seen)
        self.assertIn('comments', types_seen)



    def test_spec_multiple_include(self):
        '''Should return multiple related resource types.

        Multiple related resources can be requested in a comma-separated list:

            * GET /articles/1?include=author,comments.author
        '''
        # TODO(Colin) implement

    def test_spec_compound_full_linkage(self):
        '''All included resources should be referenced by a resource link.

        Compound documents require "full linkage", meaning that every included
        resource MUST be identified by at least one resource identifier object
        in the same document. These resource identifier objects could either be
        primary data or represent resource linkage contained within primary or
        included resources.
        '''
        # get a person with included blogs and comments.
        person = self.test_app.get('/people/1?include=blogs,comments').json
        # Find all the resource identifiers.
        rids = set()
        for rel in person['data']['relationships'].values():
            for item in rel['data']:
                rids.add((item['type'], item['id']))

        # Every included item should have an identifier somewhere.
        for item in person['included']:
            type_ = item['type']
            id_ = item['id']
            self.assertIn((type_, id_), rids)

    def test_spec_compound_no_linkage_sparse(self):
        '''Included resources not referenced if referencing field not included.

        The only exception to the full linkage requirement is when relationship
        fields that would otherwise contain linkage data are excluded via sparse
        fieldsets.
        '''
        person = self.test_app.get(
            '/people/1?include=blogs&fields[people]=name,comments'
        ).json
        # Find all the resource identifiers.
        rids = set()
        for rel in person['data']['relationships'].values():
            for item in rel['data']:
                rids.add((item['type'], item['id']))
        self.assertGreater(len(person['included']), 0)
        for blog in person['included']:
            self.assertEqual(blog['type'], 'blogs')

    def test_spec_compound_unique_resources(self):
        '''Each resource object should appear only once.

        A compound document MUST NOT include more than one resource object for
        each type and id pair.
        '''
        # get some people with included blogs and comments.
        people = self.test_app.get('/people?include=blogs,comments').json
        # Check that each resource only appears once.
        seen = set()
        # Add the main resource objects.
        for person in people['data']:
            self.assertNotIn((person['type'], person['id']), seen)
            seen.add((person['type'], person['id']))
        # Check the included resources.
        for obj in people['included']:
            self.assertNotIn((obj['type'], obj['id']), seen)
            seen.add((obj['type'], obj['id']))

    def test_spec_links(self):
        '''Links should be an object with URL strings.

        Where specified, a links member can be used to represent links. The
        value of each links member MUST be an object (a "links object").

        Each member of a links object is a “link”. A link MUST be represented as
        either:

            * a string containing the link’s URL.
            * an object ("link object") which can contain the following members:
                * href: a string containing the link’s URL.
                * meta: a meta object containing non-standard meta-information
                 about the link.

        Note: only URL string links are currently generated by jsonapi.
        '''
        links = self.test_app.get('/people').json['links']
        self.assertIsInstance(links['self'], str)
        self.assertIsInstance(links['first'], str)
        self.assertIsInstance(links['last'], str)

    def test_spec_fetch_non_existent(self):
        '''Should 404 when fetching non existent resource.

        A server MUST respond with 404 Not Found when processing a request to
        fetch a single resource that does not exist,
        '''
        r = self.test_app.get('/people/1000', status=404)

    def test_spec_fetch_non_existent_related(self):
        '''Should return primary data of null, not 404.

        null is only an appropriate response when the requested URL is one that
        might correspond to a single resource, but doesn’t currently.
        '''
        data = self.test_app.get('/comments/5/author').json['data']
        self.assertIsNone(data)

    def test_spec_fetch_relationship_link(self):
        '''relationships links should return linkage information.

        A server MUST support fetching relationship data for every relationship
        URL provided as a self link as part of a relationship’s links object

        The primary data in the response document MUST match the appropriate
        value for resource linkage, as described above for relationship objects.
        '''
        # Blogs have both many to one and one to many relationships.
        blog1 = self.test_app.get('/blogs/1').json['data']

        # to one
        owner_url = blog1['relationships']['owner']['links']['self']
        # A server MUST support fetching relationship data...
        owner_data = self.test_app.get(owner_url).json['data']
        # the response document MUST match the appropriate value for resource
        # linkage...
        #
        # In this case a resource identifier with type = 'people' and an id.
        self.assertEqual('people', owner_data['type'])
        self.assertIn('id', owner_data)

        # to one, empty relationship

        # to many
        posts_url = blog1['relationships']['posts']['links']['self']
        # A server MUST support fetching relationship data...
        posts_data = self.test_app.get(posts_url).json['data']
        # the response document MUST match the appropriate value for resource
        # linkage...
        #
        # In this case an array of 'posts' resource identifiers.
        self.assertIsInstance(posts_data, list)
        for post in posts_data:
            self.assertEqual('posts', post['type'])
            self.assertIn('id', post)

    def test_spec_fetch_relationship_to_one_empty(self):
        '''Fetching empty relationships link should give null data.

        If [a to-one] relationship is empty, then a GET request to the
        [relationship] URL would return:

            "data": null
        '''
        # comment 5 has no author
        comment5 = self.test_app.get('/comments/5').json['data']
        author = self.test_app.get(
            comment5['relationships']['author']['links']['self']
        ).json['data']
        self.assertIsNone(author)

    def test_spec_fetch_relationship_to_many_empty(self):
        '''Fetching empty relationships link should give empty array.

        If [a to-many] relationship is empty, then a GET request to the
        [relationship] URL would return:

            "data": []
        '''
        # post 1 has no comments
        post1 = self.test_app.get('/posts/1').json['data']
        comments = self.test_app.get(
            post1['relationships']['comments']['links']['self']
        ).json['data']
        self.assertEqual(len(comments), 0)

    def test_spec_fetch_not_found_relationship(self):
        '''Should 404 when fetching a relationship that does not exist.

        A server MUST return 404 Not Found when processing a request to fetch a
        relationship link URL that does not exist.
        '''
        # Try to get the author of a non existent post.
        r = self.test_app.get('/posts/1000/relationships/author', status=404)

    def test_spec_sparse_fields(self):
        '''Should return only requested fields.

        A client MAY request that an endpoint return only specific fields in the
        response on a per-type basis by including a fields[TYPE] parameter.

        The value of the fields parameter MUST be a comma-separated (U+002C
        COMMA, ",") list that refers to the name(s) of the fields to be
        returned.

        If a client requests a restricted set of fields for a given resource
        type, an endpoint MUST NOT include additional fields in resource objects
        of that type in its response.
        '''
        # Ask for just the title, content and author fields of a post.
        r = self.test_app.get('/posts/1?fields[posts]=title,content,author')
        data = r.json['data']

        atts = data['attributes']
        self.assertEqual(len(atts), 2)
        self.assertIn('title', atts)
        self.assertIn('content', atts)

        rels = data['relationships']
        self.assertEqual(len(rels), 1)
        self.assertIn('author', rels)


    def test_spec_single_sort(self):
        '''Should return  collection sorted by correct field.

        An endpoint MAY support requests to sort the primary data with a sort
        query parameter. The value for sort MUST represent sort fields.

            * GET /people?sort=age
        '''
        data = self.test_app.get('/posts?sort=content').json['data']
        prev = ''
        for item in data:
            self.assertGreaterEqual(item['attributes']['content'], prev)
            prev = item['attributes']['content']


    def test_spec_multiple_sort(self):
        '''Should return collection sorted by multiple fields, applied in order.

        An endpoint MAY support multiple sort fields by allowing comma-separated
        (U+002C COMMA, ",") sort fields. Sort fields SHOULD be applied in the
        order specified.

            * GET /people?sort=age,name
        '''
        data = self.test_app.get('/posts?sort=content,id').json['data']
        prev_content = ''
        prev_id = 0
        for item in data:
            self.assertGreaterEqual(
                item['attributes']['content'],
                prev_content
            )
            self.assertGreaterEqual(item['id'], prev_id)
            prev_content = item['attributes']['content']
            prev_id = item['id']

    def test_spec_descending_sort(self):
        '''Should return results sorted by field in reverse order.

        The sort order for each sort field MUST be ascending unless it is
        prefixed with a minus (U+002D HYPHEN-MINUS, "-"), in which case it MUST
        be descending.

            * GET /articles?sort=-created,title
        '''
        data = self.test_app.get('/posts?sort=-content').json['data']
        prev = 'zzz'
        for item in data:
            self.assertLessEqual(item['attributes']['content'], prev)
            prev = item['attributes']['content']

    # TODO(Colin) repeat sort tests for other collection returning endpoints,
    # because: Note: This section applies to any endpoint that responds with a
    # resource collection as primary data, regardless of the request type

    def test_spec_pagination_links(self):
        '''Should provide correct pagination links.

        A server MAY provide links to traverse a paginated data set ("pagination
        links").

        Pagination links MUST appear in the links object that corresponds to a
        collection. To paginate the primary data, supply pagination links in the
        top-level links object. To paginate an included collection returned in a
        compound document, supply pagination links in the corresponding links
        object.

        The following keys MUST be used for pagination links:

            * first: the first page of data
            * last: the last page of data
            * prev: the previous page of data
            * next: the next page of data
        '''
        json = self.test_app.get('/posts?page[limit]=2&page[offset]=2').json
        self.assertEqual(len(json['data']), 2)
        self.assertIn('first', json['links'])
        self.assertIn('last', json['links'])
        self.assertIn('prev', json['links'])
        self.assertIn('next', json['links'])

    def test_spec_pagination_unavailable_links(self):
        '''Next page link should not be available

        Keys MUST either be omitted or have a null value to indicate that a
        particular link is unavailable.
        '''
        r = self.test_app.get('/posts?page[limit]=1')
        available = r.json['meta']['results']['available']
        json = self.test_app.get(
            '/posts?page[limit]=2&page[offset]=' + str(available - 2)
        ).json
        self.assertEqual(len(json['data']), 2)
        self.assertNotIn('next', json['links'])

    def test_spec_pagination_order(self):
        '''Pages (and results) should order restults as per order param.

        Concepts of order, as expressed in the naming of pagination links, MUST
        remain consistent with JSON API’s sorting rules.
        '''
        data = self.test_app.get(
            '/posts?page[limit]=4&sort=content&fields[posts]=content'
        ).json['data']
        self.assertEqual(len(data), 4)
        prev = ''
        for item in data:
            self.assertGreaterEqual(item['attributes']['content'], prev)
            prev = item['attributes']['content']

    # TODO(Colin) repeat sort tests for other collection returning endpoints,
    # because: Note: This section applies to any endpoint that responds with a
    # resource collection as primary data, regardless of the request type

    def test_spec_filter(self):
        '''Should return collection with just the alice people object.

        The filter query parameter is reserved for filtering data. Servers and
        clients SHOULD use this key for filtering operations.
        '''
        data = self.test_app.get('/people?filter[name:eq]=alice').json['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['type'], 'people')
        self.assertEqual(data[0]['attributes']['name'], 'alice')

    # TODO(Colin) more filter coverage.

    def test_api_errors_structure(self):
        '''Errors should be array of objects with code, title, detail members.'''
        r = self.test_app.get(
            '/people',
            headers={ 'Content-Type': 'application/vnd.api+json; param=val' },
            status=415,
        )
        self.assertIn('errors', r.json)
        self.assertIsInstance(r.json['errors'], list)
        err = r.json['errors'][0]
        self.assertIn('code', err)
        self.assertIn('title', err)
        self.assertIn('detail', err)
