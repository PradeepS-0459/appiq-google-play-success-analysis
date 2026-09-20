# AppIQ — Testing Category-Specific vs. Universal Drivers of App Store Success Using Google Play Metadata

## Problem Statement

App publishers and product managers invest in pricing, update cadence, content rating, and feature decisions with no reliable evidence of what actually drives high ratings. Most existing app-success analyses build one universal model across the entire store, assuming that a factor which works in one category (e.g., Games) works everywhere else too. This study tests that assumption directly by building a single pooled model and separate per-category models, then comparing them to determine whether success factors generalize across categories or are category-specific.

## Objectives

1. Identify which app metadata attributes most influence whether an app is highly rated.
2. Build a pooled classification model (all categories combined) predicting high vs. low rating engagement.
3. Build separate per-category models and compare them to the pooled model.
4. Quantify whether success factors are universal or category-specific using a novel **Category Sensitivity Index** and **Cross-Category Transfer Tests**.
5. Translate findings into concrete, category-aware recommendations for app publishers.

## Data Collection

- **Source:** Google Play Store public web pages
- **Method:** Web-scraped using the `google-play-scraper` Python library — no API key or login required
- **Scale:** 10,000+ unique apps across 48 Google Play categories
- **Fields collected:** app_id, title, category, price, is_free, has_in_app_purchases, contains_ads, content_rating, size_mb, install_count, real_installs, average_rating, num_ratings, num_reviews, ratings_1_star, ratings_2_star, ratings_3_star, ratings_4_star, ratings_5_star, developer_name, released_date, last_updated_date
- **Privacy:** `developer_email` and `developer_website` are excluded at collection time (PII for indie developers)

## Methods Used

- **Data Preprocessing:** Missing-value handling, feature engineering (price_tier, size_tier, days_since_update), categorical encoding
- **Exploratory Data Analysis:** Rating distributions, correlation heatmaps, engagement analysis by price tier and content rating
- **Classification Models:** Logistic Regression, Random Forest
- **Novelty — Category Sensitivity Index:** Standard deviation of feature importances across per-category models, normalized to a 0–1 scale
- **Novelty — Cross-Category Transfer Test:** Train on category A, test on category B (no retraining) to measure accuracy drop as evidence for/against universal strategies

## Project Structure

```
├── README.md                  # This file
├── collect_data.py            # Standalone data collection script
├── analysis.ipynb             # Full analysis notebook (preprocessing → modeling → results)
├── Case_Study_Report.pdf      # Final report
└── data/
    ├── raw_apps.csv           # Raw scraped data
    └── cleaned_apps.csv       # Cleaned and feature-engineered dataset
```

## How to Run

```bash
# 1. Install dependencies
pip install google-play-scraper pandas scikit-learn matplotlib seaborn

# 2. Collect data (takes ~2-4 hours)
python collect_data.py

# 3. Open and run the analysis notebook
jupyter notebook analysis.ipynb
```


