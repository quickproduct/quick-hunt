"""
Top consulting and IT outsourcing / staffing firms with career page URLs and ATS info.

Companies in this list hire senior engineers on contracts to staff client projects
(Indian IT services giants, Big-4 consulting tech arms, global outsourcing players,
and remote-talent marketplaces).

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


class ConsultingCompany(TypedDict, total=False):
    name: str
    career_url: str
    ats: Literal["greenhouse", "lever", "smartrecruiters", "workday", "icims", "taleo", "bamboohr", "custom"]
    ats_slug: str


CONSULTING_COMPANIES: list[ConsultingCompany] = [
    # ── Indian IT services giants ────────────────────────────────────────────
    {
        "name": "TCS",
        "career_url": "https://www.tcs.com/careers/india/job-search?role=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Infosys",
        "career_url": "https://career.infosys.com/jobs?keywords=software+engineer&location=India",
        "ats": "custom",
    },
    {
        "name": "Wipro",
        "career_url": "https://careers.wipro.com/careers-home/jobs?keywords=software+engineer",
        "ats": "workday",
    },
    {
        "name": "HCLTech",
        "career_url": "https://www.hcltech.com/careers/jobs?keywords=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Tech Mahindra",
        "career_url": "https://careers.techmahindra.com/jobs.aspx?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "LTIMindtree",
        "career_url": "https://www.ltimindtree.com/careers/job-openings/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Mphasis",
        "career_url": "https://careers.mphasis.com/search-jobs?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Persistent Systems",
        "career_url": "https://www.persistent.com/careers/current-openings/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Hexaware",
        "career_url": "https://hexaware.com/careers/job-openings/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Coforge",
        "career_url": "https://www.coforge.com/careers/job-openings?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Zensar",
        "career_url": "https://www.zensar.com/careers/job-openings/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Mindtree",
        "career_url": "https://www.mindtree.com/careers/job-search?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Cyient",
        "career_url": "https://www.cyient.com/careers/job-openings?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Birlasoft",
        "career_url": "https://www.birlasoft.com/careers/job-openings?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Sonata Software",
        "career_url": "https://www.sonata-software.com/careers/job-openings?keyword=software+engineer",
        "ats": "custom",
    },

    # ── Global IT services / outsourcing ─────────────────────────────────────
    {
        "name": "Cognizant",
        "career_url": "https://careers.cognizant.com/global/en/search-results?keywords=software+engineer",
        "ats": "workday",
    },
    {
        "name": "Capgemini",
        "career_url": "https://www.capgemini.com/careers/job-search/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "IBM Consulting",
        "career_url": "https://www.ibm.com/careers/search?q=software+engineer&category=Consulting",
        "ats": "workday",
    },
    {
        "name": "Accenture",
        "career_url": "https://www.accenture.com/in-en/careers/jobsearch?jk=software+engineer",
        "ats": "workday",
    },
    {
        "name": "DXC Technology",
        "career_url": "https://dxc.wd1.myworkdayjobs.com/Careers?q=software+engineer",
        "ats": "workday",
    },
    {
        "name": "Atos",
        "career_url": "https://atos.net/en/careers/job-search?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "NTT Data",
        "career_url": "https://careers-inc.nttdata.com/search/?q=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Fujitsu",
        "career_url": "https://www.fujitsu.com/global/about/careers/jobsearch/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Unisys",
        "career_url": "https://www.unisys.com/careers/job-search?keyword=software+engineer",
        "ats": "workday",
    },
    {
        "name": "CGI",
        "career_url": "https://www.cgi.com/en/careers/find-job?keyword=software+engineer",
        "ats": "custom",
    },

    # ── Big-4 consulting (tech arms) ─────────────────────────────────────────
    {
        "name": "Deloitte",
        "career_url": "https://apply.deloitte.com/en_US/careers/SearchJobs/software-engineer",
        "ats": "custom",
    },
    {
        "name": "EY",
        "career_url": "https://careers.ey.com/ey/search/?q=software+engineer",
        "ats": "custom",
    },
    {
        "name": "PwC",
        "career_url": "https://jobs.us.pwc.com/search-jobs/software+engineer",
        "ats": "custom",
    },
    {
        "name": "KPMG",
        "career_url": "https://home.kpmg/xx/en/home/careers/job-search.html?keyword=software+engineer",
        "ats": "workday",
    },
    {
        "name": "McKinsey Digital",
        "career_url": "https://www.mckinsey.com/careers/search-jobs?keywords=software+engineer",
        "ats": "custom",
    },
    {
        "name": "BCG X",
        "career_url": "https://careers.bcg.com/global/en/c/bcg-x-jobs",
        "ats": "custom",
    },
    {
        "name": "Bain",
        "career_url": "https://www.bain.com/careers/find-a-role/?keyword=software+engineer",
        "ats": "custom",
    },

    # ── Mid-size / specialist consulting & engineering ───────────────────────
    {
        "name": "EPAM",
        "career_url": "https://www.epam.com/careers/job-listings?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Globant",
        "career_url": "https://www.globant.com/careers/jobs?keyword=software+engineer",
        "ats": "greenhouse",
        "ats_slug": "globant",
    },
    {
        "name": "ThoughtWorks",
        "career_url": "https://www.thoughtworks.com/careers/jobs?keyword=software+engineer",
        "ats": "smartrecruiters",
        "ats_slug": "ThoughtWorks2",
    },
    {
        "name": "GlobalLogic",
        "career_url": "https://www.globallogic.com/careers/job-openings/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Endava",
        "career_url": "https://careers.endava.com/jobs?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Virtusa",
        "career_url": "https://www.virtusa.com/careers/job-openings?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Mu Sigma",
        "career_url": "https://www.mu-sigma.com/careers/openings?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Fractal Analytics",
        "career_url": "https://fractal.ai/careers/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "Tiger Analytics",
        "career_url": "https://www.tigeranalytics.com/careers/?keyword=software+engineer",
        "ats": "custom",
    },
    {
        "name": "ZS Associates",
        "career_url": "https://www.zs.com/careers/job-search?keyword=software+engineer",
        "ats": "workday",
    },

    # ── Remote talent marketplaces / staffing ────────────────────────────────
    {
        "name": "Toptal",
        "career_url": "https://www.toptal.com/careers#jobs",
        "ats": "greenhouse",
        "ats_slug": "toptal",
    },
    {
        "name": "Turing",
        "career_url": "https://www.turing.com/jobs",
        "ats": "custom",
    },
    {
        "name": "Andela",
        "career_url": "https://andela.com/careers/",
        "ats": "greenhouse",
        "ats_slug": "andela",
    },
    {
        "name": "Crossover",
        "career_url": "https://www.crossover.com/jobs",
        "ats": "custom",
    },
    {
        "name": "Gun.io",
        "career_url": "https://gun.io/find-work/",
        "ats": "custom",
    },
    {
        "name": "Arc",
        "career_url": "https://arc.dev/remote-jobs",
        "ats": "custom",
    },
    {
        "name": "X-Team",
        "career_url": "https://x-team.com/remote-developer-jobs/",
        "ats": "custom",
    },
    {
        "name": "10Pearls",
        "career_url": "https://10pearls.com/careers/?keyword=software+engineer",
        "ats": "custom",
    },
]
