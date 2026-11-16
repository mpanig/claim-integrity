"""Site and entity audits for AI visibility.

Only URLs a user entered (or the brand pages on its truth sheets) are fetched, one page at a
time, after checking robots.txt, with an honest User-Agent. Nothing impersonates AI crawlers:
crawlability is read from robots.txt rules and page tags, not by pretending to be a bot.
"""
