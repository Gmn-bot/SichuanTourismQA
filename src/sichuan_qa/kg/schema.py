"""图谱本体：英文标签，供 Text2Cypher / 约束查询共用。"""

from __future__ import annotations

ATTRACTION_LABEL = "Attraction"
CITY_LABEL = "City"
TAG_LABEL = "Tag"
FACILITY_LABEL = "Facility"

REL_IN_CITY = "IN_CITY"
REL_HAS_TAG = "HAS_TAG"
REL_HAS_FACILITY = "HAS_FACILITY"
REL_NEAR = "NEAR"

PREDICATE_TO_PROP = {
    "位于": "address",
    "的评分是": "rating",
    "的热度为": "popularity",
    "的开放时间为": "opening_time",
    "的官方电话是": "phone",
    "的介绍是": "introduction",
    "的优待政策是": "discount_policy",
    "的服务设施包括": "facilities_text",
    "的URL是": "website",
}

CITY_PREDICATE = "属于城市"

FACT_ATTRIBUTES = (
    "address",
    "opening_time",
    "phone",
    "rating",
    "popularity",
    "website",
    "ticket_info",
    "introduction",
    "discount_policy",
)

ATTR_ALIASES = {
    "地址": "address",
    "开放时间": "opening_time",
    "电话": "phone",
    "评分": "rating",
    "热度": "popularity",
    "官网": "website",
    "门票价格": "ticket_info",
    "门票": "ticket_info",
    "简介": "introduction",
    "介绍": "introduction",
}

FLOAT_PROPS = {"rating", "popularity"}

CONSTRAINT_STATEMENTS = [
    f"CREATE CONSTRAINT attraction_name IF NOT EXISTS FOR (a:{ATTRACTION_LABEL}) REQUIRE a.name IS UNIQUE",
    f"CREATE CONSTRAINT city_name IF NOT EXISTS FOR (c:{CITY_LABEL}) REQUIRE c.name IS UNIQUE",
    f"CREATE CONSTRAINT tag_name IF NOT EXISTS FOR (t:{TAG_LABEL}) REQUIRE t.name IS UNIQUE",
    f"CREATE CONSTRAINT facility_name IF NOT EXISTS FOR (f:{FACILITY_LABEL}) REQUIRE f.name IS UNIQUE",
]

FULLTEXT_INDEX = (
    "CREATE FULLTEXT INDEX attraction_fulltext IF NOT EXISTS "
    f"FOR (a:{ATTRACTION_LABEL}) ON EACH [a.name, a.introduction, a.address]"
)

SCHEMA_FOR_LLM = """
Nodes:
  (a:Attraction {name, address, rating, popularity, opening_time, phone,
                 introduction, discount_policy, website, ticket_info, is_free})
  (c:City {name})
  (t:Tag {name})
  (f:Facility {name})
Relationships:
  (a)-[:IN_CITY]->(c)
  (a)-[:HAS_TAG]->(t)
  (a)-[:HAS_FACILITY]->(f)
  (a)-[:NEAR]->(a2:Attraction)
""".strip()
