"""
Top MNC companies with career page URLs and ATS platform info.

ats values and their scraping tier:
  greenhouse      (Tier 1) httpx — boards-api.greenhouse.io public JSON API
  lever           (Tier 2) httpx — api.lever.co public JSON API
  smartrecruiters (Tier 3) httpx — api.smartrecruiters.com public JSON API
  workday         (Tier 4) Playwright + BS4 — Workday React pages
  icims           (Tier 5) Playwright + BS4 — iCIMS career pages
  taleo           (Tier 6) httpx + BS4 — Oracle Taleo HTML tables
  bamboohr        (Tier 7) Playwright + BS4 — BambooHR React pages
  custom          (Tier 8) Playwright + BS4 enhanced — generic fallback

ats_slug is required only for greenhouse, lever, and smartrecruiters.
"""

from typing import TypedDict, Literal


class MNCCompany(TypedDict, total=False):
    name: str
    career_url: str
    ats: Literal["greenhouse", "lever", "smartrecruiters", "workday", "icims", "taleo", "bamboohr", "custom"]
    ats_slug: str  # required when ats is greenhouse / lever / smartrecruiters


MNC_COMPANIES: list[MNCCompany] = [

    # ── FAANG / Big Tech ──────────────────────────────────────────────────────
    {
        "name": "Google",
        "career_url": "https://careers.google.com/jobs/results/?q=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Microsoft",
        "career_url": "https://jobs.microsoft.com/en-us/search?q=software+engineer&lc=India",
        "ats": "workday",
    },
    {
        "name": "Amazon",
        "career_url": "https://www.amazon.jobs/en/search?base_query=software+engineer&loc_query=India",
        "ats": "custom",
    },
    {
        "name": "Meta",
        "career_url": "https://www.metacareers.com/jobs?q=software+engineer&roles[0]=eng",
        "ats": "custom",
    },
    {
        "name": "Apple",
        "career_url": "https://jobs.apple.com/en-us/search?search=software+engineer&sort=relevance",
        "ats": "custom",
    },
    {
        "name": "Netflix",
        "career_url": "https://jobs.netflix.com/search?q=software+engineer",
        "ats": "greenhouse",
        "ats_slug": "netflix",
    },
    {
        "name": "Uber",
        "career_url": "https://www.uber.com/us/en/careers/list/?query=software+engineer",
        "ats": "greenhouse",
        "ats_slug": "uber",
    },
    {
        "name": "Airbnb",
        "career_url": "https://careers.airbnb.com",
        "ats": "greenhouse",
        "ats_slug": "airbnb",
    },
    {
        "name": "Twitter / X",
        "career_url": "https://careers.x.com/en",
        "ats": "custom",
    },
    {
        "name": "LinkedIn",
        "career_url": "https://careers.linkedin.com/jobs?keywords=software+engineer",
        "ats": "workday",
    },

    # ── Enterprise Tech ───────────────────────────────────────────────────────
    {
        "name": "Salesforce",
        "career_url": "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site?q=software+engineer",
        "ats": "workday",
    },
    {
        "name": "Oracle",
        "career_url": "https://careers.oracle.com/jobs/#en/sites/jobsearch/requisitions?keyword=Software+Engineer&location=India",
        "ats": "custom",
    },
    {
        "name": "SAP",
        "career_url": "https://jobs.sap.com/search/?q=software+engineer&locname=India",
        "ats": "custom",
    },
    {
        "name": "IBM",
        "career_url": "https://www.ibm.com/employment/#jobs?%23jobs=&job_field[]=software-engineering&country=india",
        "ats": "custom",
    },
    {
        "name": "Cisco",
        "career_url": "https://jobs.cisco.com/jobs/SearchJobs/software%20engineer?21178=%5B169482%5D&21178_format=6020&listFilterMode=1",
        "ats": "workday",
    },
    {
        "name": "Intel",
        "career_url": "https://jobs.intel.com/en/search-jobs/software%20engineer/India/599/1/2/6252001/23.43,80.97/20/1",
        "ats": "workday",
    },
    {
        "name": "Dell Technologies",
        "career_url": "https://jobs.dell.com/en/search-jobs/software%20engineer/India/375/1/2/6252001/23.43,80.97/20/1",
        "ats": "workday",
    },
    {
        "name": "HP",
        "career_url": "https://jobs.hp.com/jobsearch/SearchJobs/software%20engineer?3_119_3=117",
        "ats": "taleo",
    },
    {
        "name": "Qualcomm",
        "career_url": "https://careers.qualcomm.com/careers/search?keywords=software+engineer&country=India",
        "ats": "workday",
    },
    {
        "name": "NVIDIA",
        "career_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite?q=software+engineer",
        "ats": "workday",
    },

    # ── Cloud / SaaS ──────────────────────────────────────────────────────────
    {
        "name": "Atlassian",
        "career_url": "https://www.atlassian.com/company/careers/all-jobs?team=Engineering&location=India",
        "ats": "greenhouse",
        "ats_slug": "atlassian",
    },
    {
        "name": "Stripe",
        "career_url": "https://stripe.com/jobs/search?teams=Engineering",
        "ats": "greenhouse",
        "ats_slug": "stripe",
    },
    {
        "name": "Shopify",
        "career_url": "https://www.shopify.com/careers/search?keywords=software+engineer",
        "ats": "greenhouse",
        "ats_slug": "shopify",
    },
    {
        "name": "Zoom",
        "career_url": "https://careers.zoom.us/jobs#",
        "ats": "greenhouse",
        "ats_slug": "zoom",
    },
    {
        "name": "Twilio",
        "career_url": "https://www.twilio.com/company/jobs",
        "ats": "greenhouse",
        "ats_slug": "twilio",
    },
    {
        "name": "Datadog",
        "career_url": "https://www.datadoghq.com/careers/detail/",
        "ats": "greenhouse",
        "ats_slug": "datadog",
    },
    {
        "name": "Cloudflare",
        "career_url": "https://www.cloudflare.com/careers/jobs/",
        "ats": "greenhouse",
        "ats_slug": "cloudflare",
    },
    {
        "name": "HubSpot",
        "career_url": "https://www.hubspot.com/careers/jobs",
        "ats": "greenhouse",
        "ats_slug": "hubspot",
    },
    {
        "name": "Zendesk",
        "career_url": "https://jobs.zendesk.com/us/en/search-results?keywords=software+engineer",
        "ats": "smartrecruiters",
        "ats_slug": "Zendesk",
    },
    {
        "name": "HashiCorp",
        "career_url": "https://www.hashicorp.com/careers",
        "ats": "greenhouse",
        "ats_slug": "hashicorp",
    },
    {
        "name": "MongoDB",
        "career_url": "https://www.mongodb.com/careers",
        "ats": "greenhouse",
        "ats_slug": "mongodb",
    },
    {
        "name": "Okta",
        "career_url": "https://www.okta.com/company/careers/",
        "ats": "greenhouse",
        "ats_slug": "okta",
    },
    {
        "name": "Elastic",
        "career_url": "https://www.elastic.co/about/careers",
        "ats": "greenhouse",
        "ats_slug": "elastic",
    },
    {
        "name": "New Relic",
        "career_url": "https://newrelic.com/about/culture-and-careers",
        "ats": "lever",
        "ats_slug": "newrelic",
    },
    {
        "name": "PagerDuty",
        "career_url": "https://www.pagerduty.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "pagerduty",
    },
    {
        "name": "Snowflake",
        "career_url": "https://careers.snowflake.com/us/en/search-results?keywords=software+engineer",
        "ats": "workday",
    },
    {
        "name": "Splunk",
        "career_url": "https://www.splunk.com/en_us/careers/search-jobs.html?keyword=software+engineer",
        "ats": "workday",
    },
    {
        "name": "ServiceNow",
        "career_url": "https://careers.servicenow.com/careers/jobs?keywords=software+engineer&location=India",
        "ats": "workday",
    },
    {
        "name": "Workday",
        "career_url": "https://workday.wd5.myworkdayjobs.com/Workday?q=software+engineer",
        "ats": "workday",
    },
    {
        "name": "Palo Alto Networks",
        "career_url": "https://jobs.paloaltonetworks.com/en/search-jobs/Software+Engineer/India/30832/1/2/6252001/23.43,80.97/20/1",
        "ats": "workday",
    },
    {
        "name": "VMware",
        "career_url": "https://careers.vmware.com/main/jobs?keywords=software+engineer&location=India",
        "ats": "custom",
    },
    {
        "name": "Adobe",
        "career_url": "https://adobe.wd5.myworkdayjobs.com/external_experienced?q=software+engineer",
        "ats": "workday",
    },

    # ── Fintech ───────────────────────────────────────────────────────────────
    {
        "name": "PayPal",
        "career_url": "https://careers.paypal.com/jobs/search?keywords=software+engineer&location=India",
        "ats": "custom",
    },
    {
        "name": "Square / Block",
        "career_url": "https://careers.squareup.com/us/en/jobs?keywords=software+engineer",
        "ats": "greenhouse",
        "ats_slug": "square",
    },
    {
        "name": "Coinbase",
        "career_url": "https://www.coinbase.com/careers/positions?department=Engineering",
        "ats": "greenhouse",
        "ats_slug": "coinbase",
    },
    {
        "name": "Brex",
        "career_url": "https://www.brex.com/careers",
        "ats": "greenhouse",
        "ats_slug": "brex",
    },
    {
        "name": "Plaid",
        "career_url": "https://plaid.com/careers/",
        "ats": "lever",
        "ats_slug": "plaid",
    },
    {
        "name": "Razorpay",
        "career_url": "https://razorpay.com/jobs/",
        "ats": "lever",
        "ats_slug": "razorpay",
    },
    {
        "name": "Stripe India",
        "career_url": "https://stripe.com/jobs/search?teams=Engineering&location=India",
        "ats": "greenhouse",
        "ats_slug": "stripe",
    },

    # ── Indian IT Services ────────────────────────────────────────────────────
    {
        "name": "Infosys",
        "career_url": "https://career.infosys.com/joblist#SearchKey=software engineer",
        "ats": "custom",
    },
    {
        "name": "TCS",
        "career_url": "https://www.tcs.com/careers/tcs-careers-openings",
        "ats": "custom",
    },
    {
        "name": "Wipro",
        "career_url": "https://careers.wipro.com/careers-home/jobs?keyword=software+engineer",
        "ats": "workday",
    },
    {
        "name": "HCL Technologies",
        "career_url": "https://www.hcltech.com/careers/jobs?jobtitle=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Tech Mahindra",
        "career_url": "https://careers.techmahindra.com/search/?createNewAlert=false&q=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Mphasis",
        "career_url": "https://careers.mphasis.com",
        "ats": "greenhouse",
        "ats_slug": "mphasis",
    },
    {
        "name": "Persistent Systems",
        "career_url": "https://www.persistent.com/careers/search-jobs/?query=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Hexaware",
        "career_url": "https://hexaware.com/careers/?search=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Cognizant",
        "career_url": "https://careers.cognizant.com/global/en/search-results?keywords=software+engineer",
        "ats": "workday",
    },
    {
        "name": "Capgemini",
        "career_url": "https://www.capgemini.com/careers/job-search/?search_term=software+engineer&country=IN",
        "ats": "custom",
    },
    {
        "name": "Accenture",
        "career_url": "https://www.accenture.com/in-en/careers/explore-careers/search-jobs?jk=software+engineer",
        "ats": "workday",
    },
    {
        "name": "L&T Technology",
        "career_url": "https://www.ltts.com/careers/job-openings?search=software+engineer",
        "ats": "custom",
    },

    # ── Indian Product / Startup Unicorns ─────────────────────────────────────
    {
        "name": "Flipkart",
        "career_url": "https://www.flipkartcareers.com/#!/joblist",
        "ats": "lever",
        "ats_slug": "flipkart",
    },
    {
        "name": "Paytm",
        "career_url": "https://jobs.lever.co/paytm",
        "ats": "lever",
        "ats_slug": "paytm",
    },
    {
        "name": "Swiggy",
        "career_url": "https://careers.swiggy.com/#/",
        "ats": "lever",
        "ats_slug": "swiggy",
    },
    {
        "name": "Zomato",
        "career_url": "https://www.zomato.com/careers",
        "ats": "greenhouse",
        "ats_slug": "zomato",
    },
    {
        "name": "CRED",
        "career_url": "https://careers.cred.club",
        "ats": "lever",
        "ats_slug": "dreamplug",
    },
    {
        "name": "PhonePe",
        "career_url": "https://www.phonepe.com/careers/",
        "ats": "lever",
        "ats_slug": "phonepe",
    },
    {
        "name": "Meesho",
        "career_url": "https://careers.meesho.com",
        "ats": "lever",
        "ats_slug": "meesho",
    },
    {
        "name": "Freshworks",
        "career_url": "https://www.freshworks.com/company/careers/",
        "ats": "greenhouse",
        "ats_slug": "freshworks",
    },
    {
        "name": "Postman",
        "career_url": "https://www.postman.com/company/careers/",
        "ats": "greenhouse",
        "ats_slug": "postman",
    },
    {
        "name": "BrowserStack",
        "career_url": "https://www.browserstack.com/careers",
        "ats": "lever",
        "ats_slug": "browserstack",
    },
    {
        "name": "Zoho",
        "career_url": "https://careers.zohocorp.com/jobs/Careers/software-engineer",
        "ats": "custom",
    },
    {
        "name": "OLX",
        "career_url": "https://careers.olx.com",
        "ats": "greenhouse",
        "ats_slug": "olxgroup",
    },
    {
        "name": "Dream11",
        "career_url": "https://careers.dream11.com",
        "ats": "greenhouse",
        "ats_slug": "dream11",
    },
    {
        "name": "Byju's",
        "career_url": "https://careers.byjus.com",
        "ats": "greenhouse",
        "ats_slug": "byjus",
    },
    {
        "name": "Unacademy",
        "career_url": "https://unacademy.com/careers",
        "ats": "lever",
        "ats_slug": "unacademy",
    },
    {
        "name": "MakeMyTrip",
        "career_url": "https://careers.makemytrip.com/jobs?q=software+engineer",
        "ats": "custom",
    },
    {
        "name": "ShareChat",
        "career_url": "https://sharechat.com/careers",
        "ats": "greenhouse",
        "ats_slug": "sharechat",
    },
    {
        "name": "Zerodha",
        "career_url": "https://zerodha.com/careers/",
        "ats": "custom",
    },
    {
        "name": "Groww",
        "career_url": "https://groww.in/careers",
        "ats": "lever",
        "ats_slug": "groww",
    },
    {
        "name": "Cars24",
        "career_url": "https://www.cars24.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "cars24",
    },
    {
        "name": "Urban Company",
        "career_url": "https://careers.urbancompany.com",
        "ats": "greenhouse",
        "ats_slug": "urbancompany",
    },
    {
        "name": "Acko",
        "career_url": "https://acko.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "acko",
    },
    {
        "name": "Khatabook",
        "career_url": "https://khatabook.com/careers/",
        "ats": "lever",
        "ats_slug": "khatabook",
    },
    {
        "name": "BharatPe",
        "career_url": "https://bharatpe.com/careers",
        "ats": "greenhouse",
        "ats_slug": "bharatpe",
    },
    {
        "name": "Moengage",
        "career_url": "https://www.moengage.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "moengage",
    },
    {
        "name": "Zetwerk",
        "career_url": "https://www.zetwerk.com/careers/",
        "ats": "lever",
        "ats_slug": "zetwerk",
    },
    {
        "name": "Spinny",
        "career_url": "https://www.spinny.com/careers/",
        "ats": "lever",
        "ats_slug": "spinny",
    },
    {
        "name": "Dunzo",
        "career_url": "https://www.dunzo.com/careers",
        "ats": "greenhouse",
        "ats_slug": "dunzo",
    },
    {
        "name": "Blinkit",
        "career_url": "https://blinkit.com/careers",
        "ats": "custom",
    },
    {
        "name": "Zepto",
        "career_url": "https://www.zepto.com/careers",
        "ats": "custom",
    },
    {
        "name": "Cashfree",
        "career_url": "https://www.cashfree.com/careers/",
        "ats": "lever",
        "ats_slug": "cashfree",
    },
    {
        "name": "Innovaccer",
        "career_url": "https://innovaccer.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "innovaccer",
    },
    {
        "name": "Mindtickle",
        "career_url": "https://www.mindtickle.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "mindtickle",
    },
    {
        "name": "Sprinklr",
        "career_url": "https://www.sprinklr.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "sprinklr",
    },
    {
        "name": "Icertis",
        "career_url": "https://www.icertis.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "icertis",
    },
    {
        "name": "Druva",
        "career_url": "https://www.druva.com/company/careers/",
        "ats": "greenhouse",
        "ats_slug": "druva",
    },
    {
        "name": "Chargebee",
        "career_url": "https://www.chargebee.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "chargebee",
    },
    {
        "name": "CleverTap",
        "career_url": "https://clevertap.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "clevertap",
    },
    {
        "name": "Whatfix",
        "career_url": "https://www.whatfix.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "whatfix",
    },
    {
        "name": "Hasura",
        "career_url": "https://hasura.io/careers/",
        "ats": "lever",
        "ats_slug": "hasura",
    },
    {
        "name": "Darwinbox",
        "career_url": "https://darwinbox.com/careers",
        "ats": "greenhouse",
        "ats_slug": "darwinbox",
    },
    {
        "name": "Leadsquared",
        "career_url": "https://www.leadsquared.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "leadsquared",
    },
    {
        "name": "Practo",
        "career_url": "https://www.practo.com/company/careers",
        "ats": "lever",
        "ats_slug": "practo",
    },
    {
        "name": "PharmEasy",
        "career_url": "https://careers.pharmeasy.in",
        "ats": "lever",
        "ats_slug": "pharmeasy",
    },
    {
        "name": "Vedantu",
        "career_url": "https://www.vedantu.com/page/careers",
        "ats": "greenhouse",
        "ats_slug": "vedantu",
    },
    {
        "name": "Hotstar",
        "career_url": "https://careers.hotstar.com",
        "ats": "greenhouse",
        "ats_slug": "hotstar",
    },
    {
        "name": "Juspay",
        "career_url": "https://careers.juspay.in",
        "ats": "greenhouse",
        "ats_slug": "juspay",
    },
    {
        "name": "Games24x7",
        "career_url": "https://www.games24x7.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "games24x7",
    },
    {
        "name": "MPL",
        "career_url": "https://www.mpl.live/careers",
        "ats": "greenhouse",
        "ats_slug": "mobilepremierleague",
    },
    {
        "name": "Fi Money",
        "career_url": "https://fi.money/about/careers",
        "ats": "lever",
        "ats_slug": "epifi",
    },
    {
        "name": "Jupiter",
        "career_url": "https://jupiter.money/careers/",
        "ats": "lever",
        "ats_slug": "jupiter",
    },
    {
        "name": "Fampay",
        "career_url": "https://fampay.in/careers/",
        "ats": "lever",
        "ats_slug": "fampay",
    },
    {
        "name": "Volopay",
        "career_url": "https://www.volopay.com/careers",
        "ats": "lever",
        "ats_slug": "volopay",
    },
    {
        "name": "Simpl",
        "career_url": "https://getsimpl.com/careers/",
        "ats": "lever",
        "ats_slug": "simpl",
    },
    {
        "name": "Setu",
        "career_url": "https://setu.co/careers",
        "ats": "lever",
        "ats_slug": "setu",
    },
    {
        "name": "Exotel",
        "career_url": "https://exotel.com/company/careers/",
        "ats": "lever",
        "ats_slug": "exotel",
    },

    # ── Global Consulting / Services ─────────────────────────────────────────
    {
        "name": "Deloitte",
        "career_url": "https://apply.deloitte.com/careers/SearchJobs/software+engineer?3_79_3=73",
        "ats": "taleo",
    },
    {
        "name": "EY",
        "career_url": "https://careers.ey.com/ey/search/?q=software+engineer&locationsearch=India",
        "ats": "custom",
    },
    {
        "name": "PwC",
        "career_url": "https://www.pwc.com/gx/en/careers/experienced-jobs.html",
        "ats": "custom",
    },
    {
        "name": "KPMG",
        "career_url": "https://home.kpmg/in/en/home/careers.html",
        "ats": "custom",
    },
    {
        "name": "McKinsey",
        "career_url": "https://www.mckinsey.com/careers/search-jobs#",
        "ats": "custom",
    },

    # ── Telecom / Hardware ────────────────────────────────────────────────────
    {
        "name": "Jio",
        "career_url": "https://careers.jio.com/jobs?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Airtel",
        "career_url": "https://www.airtel.in/careers/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Samsung R&D India",
        "career_url": "https://www.samsung.com/global/business/networks/careers/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Motorola Solutions",
        "career_url": "https://motorolasolutions.wd5.myworkdayjobs.com/Careers?q=software+engineer",
        "ats": "workday",
    },

    # ── E-Commerce / Logistics ────────────────────────────────────────────────
    {
        "name": "Myntra",
        "career_url": "https://careers.myntra.com",
        "ats": "greenhouse",
        "ats_slug": "myntra",
    },
    {
        "name": "Delhivery",
        "career_url": "https://www.delhivery.com/careers",
        "ats": "lever",
        "ats_slug": "delhivery",
    },
    {
        "name": "Shiprocket",
        "career_url": "https://careers.shiprocket.in",
        "ats": "lever",
        "ats_slug": "shiprocket",
    },

    # ── Global Remote-Friendly ────────────────────────────────────────────────
    {
        "name": "GitLab",
        "career_url": "https://about.gitlab.com/jobs/",
        "ats": "greenhouse",
        "ats_slug": "gitlab",
    },
    {
        "name": "Automattic",
        "career_url": "https://automattic.com/work-with-us/",
        "ats": "greenhouse",
        "ats_slug": "automattic",
    },
    {
        "name": "Remote",
        "career_url": "https://remote.com/careers",
        "ats": "greenhouse",
        "ats_slug": "remote",
    },
    {
        "name": "Deel",
        "career_url": "https://www.letsdeel.com/careers",
        "ats": "greenhouse",
        "ats_slug": "deel",
    },
    {
        "name": "Loom",
        "career_url": "https://www.loom.com/careers",
        "ats": "greenhouse",
        "ats_slug": "loom",
    },
    {
        "name": "Linear",
        "career_url": "https://linear.app/careers",
        "ats": "lever",
        "ats_slug": "linear",
    },
    {
        "name": "Vercel",
        "career_url": "https://vercel.com/careers",
        "ats": "lever",
        "ats_slug": "vercel",
    },
    {
        "name": "Supabase",
        "career_url": "https://supabase.com/careers",
        "ats": "greenhouse",
        "ats_slug": "supabase",
    },
    {
        "name": "PlanetScale",
        "career_url": "https://planetscale.com/careers",
        "ats": "greenhouse",
        "ats_slug": "planetscale",
    },
    {
        "name": "Railway",
        "career_url": "https://railway.app/careers",
        "ats": "lever",
        "ats_slug": "railway",
    },
    {
        "name": "Basecamp",
        "career_url": "https://basecamp.com/about/jobs",
        "ats": "custom",
    },
]


# Deduplicate by name (safety guard)
_seen: set[str] = set()
_deduped: list[MNCCompany] = []
for _c in MNC_COMPANIES:
    _key = _c["name"].lower()
    if _key not in _seen:
        _seen.add(_key)
        _deduped.append(_c)
MNC_COMPANIES = _deduped
