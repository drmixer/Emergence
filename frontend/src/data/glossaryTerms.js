export const GLOSSARY_TERMS = [
    {
        key: 'run',
        label: 'Run',
        shortLabel: 'run',
        definition: 'A single simulation execution window with one run ID and fixed settings.',
    },
    {
        key: 'season',
        label: 'Season',
        shortLabel: 'season',
        definition: 'A bundle of 4 runs grouped under one primary hypothesis.',
    },
    {
        key: 'epoch',
        label: 'Epoch',
        shortLabel: 'epoch',
        definition: 'A bundle of 4 seasons used as the cycle boundary for tournament selection.',
    },
    {
        key: 'tournament',
        label: 'Tournament',
        shortLabel: 'tournament',
        definition: 'A special exploratory run after an epoch with selected champions, labeled separately from baseline research runs and allowed continuity-protective deterministic fallback.',
    },
    {
        key: 'carryover',
        label: 'Carryover',
        shortLabel: 'carryover',
        definition: 'When selected agent identities continue into the next season with preserved long-term memory summary.',
    },
    {
        key: 'cohort',
        label: 'Cohort',
        shortLabel: 'cohort',
        definition: 'A grouped set of agents assigned to the same model/capability routing profile for attribution-safe comparisons.',
    },
    {
        key: 'tier',
        label: 'Tier',
        shortLabel: 'tier',
        definition: 'The capability/cost band assigned to an agent at seeding. Tier 1 is the strongest and most expensive routing mix, while Tier 4 is the lightest and cheapest. Tiers create cognitive diversity; they are not hard-coded castes or fixed strategic roles.',
    },
    {
        key: 'exploratory',
        label: 'Exploratory Run',
        shortLabel: 'exploratory',
        definition: 'A run class used for showcase or stress-testing scenarios that is excluded from baseline condition synthesis by default and may use labeled routine continuity protection on terminal LLM failure.',
    },
    {
        key: 'canonical-identity',
        label: 'Canonical Identity',
        shortLabel: 'canonical identity',
        definition: 'The stable identity key Agent #NN used for attribution, analytics, and longitudinal tracking regardless of codename display.',
    },
    {
        key: 'condition',
        label: 'Condition',
        shortLabel: 'condition',
        definition: 'A named experimental setup variant used for controlled comparisons across multiple runs.',
    },
    {
        key: 'replicate',
        label: 'Replicate',
        shortLabel: 'replicate',
        definition: 'Another run executed under the same condition to test whether an observed pattern is consistent.',
    },
    {
        key: 'evidence-provenance',
        label: 'Evidence Provenance',
        shortLabel: 'evidence provenance',
        definition: 'Trace metadata describing where a displayed metric or event came from, including run ID, time window, and source.',
    },
]

export const GLOSSARY_TERMS_BY_KEY = Object.fromEntries(
    GLOSSARY_TERMS.map((term) => [term.key, term]),
)
