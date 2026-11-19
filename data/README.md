# Data

## Source

**Criteo Attribution Modeling for Bidding Dataset**, released by Criteo AI Lab:
https://ailab.criteo.com/criteo-attribution-modeling-bidding-dataset/

It is a sample of 30 days of live Criteo traffic. Each row is one ad impression
that Criteo bought in a real-time second-price auction and showed to a user.

| | |
|---|---|
| Impressions | 16.5M |
| Campaigns | about 700 |
| Conversions | about 45K |
| Size | 623 MB compressed, 2.4 GB uncompressed |

Criteo transformed the `cost` and `cpo` values before release, so they are not
real currency amounts. They are consistent across the dataset, which is what
matters for comparing strategies.

## Getting the full file

1. Download the zip from the page above ("Download instructions", then "click here").
2. Unzip it and put `criteo_attribution_dataset.tsv.gz` in `data/raw/`.
3. Run `make all`.

The full file is not committed to this repo because of its size.

## The sample in this repo

`sample/criteo_sample.tsv.gz` is a 1% sample of users from the full file,
made with `python -m adauction sample`. Sampling is by user, so each sampled
user keeps their complete history and conversion journeys are not cut in half.
CI runs the whole pipeline on it.

## Columns

| Column | Meaning |
|---|---|
| `timestamp` | Seconds since the first impression in the dataset (rows are sorted by it) |
| `uid` | User id |
| `campaign` | Campaign id |
| `conversion` | 1 if the user converted within 30 days after this impression |
| `conversion_timestamp` | Time of that conversion, or -1 |
| `conversion_id` | Id of that conversion, or -1 |
| `attribution` | 1 if the advertiser attributed the conversion to Criteo |
| `click` | 1 if this impression was clicked |
| `click_pos` | Position of this click among the clicks before the conversion (0 = first) |
| `click_nb` | Number of clicks before the conversion |
| `cost` | Price paid for this impression (transformed) |
| `cpo` | Cost per order for an attributed conversion (transformed) |
| `time_since_last_click` | Seconds since the user's previous click, or -1 |
| `cat1` to `cat9` | Anonymized contextual features |

## License and citation

The dataset is licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), and so is
the sample in this folder. Paper:

> Eustache Diemert, Julien Meynet, Pierre Galland, Damien Lefortier.
> *Attribution Modeling Increases Efficiency of Bidding in Display Advertising.*
> AdKDD & TargetAd Workshop, KDD 2017. https://arxiv.org/abs/1707.06409
