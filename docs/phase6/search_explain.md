Datenbank-Locale: collate=en_US.utf8 ctype=en_US.utf8
Trigramme für 'リザードン': ['0xe56bda', '0x1e6129', '0x475e12', '0x498314', '0x649560', '0x6af910']
Trigramm-Schwelle: 0.6

search_cards('glurak'): 219 ms
search_cards('pikachu'): 173 ms
search_cards('nachtara 215'): 140 ms

Schreibweisen für 'glurak': ['glurak', 'リザードン', '리자몽', '噴火龍', '喷火龙']

## 'glurak': 13 ms
    Limit  (cost=3291.59..3291.67 rows=30 width=13) (actual time=1.456..1.462 rows=30 loops=1)
      Buffers: shared hit=155
      ->  Sort  (cost=3291.59..3295.61 rows=1608 width=13) (actual time=1.454..1.457 rows=30 loops=1)
            Sort Key: (max(word_similarity('glurak'::text, lower((name)::text)))) DESC
            Sort Method: top-N heapsort  Memory: 26kB
            Buffers: shared hit=155
            ->  HashAggregate  (cost=3228.02..3244.10 rows=1608 width=13) (actual time=1.414..1.432 rows=109 loops=1)
                  Group Key: external_id
                  Batches: 1  Memory Usage: 73kB
                  Buffers: shared hit=155
                  ->  Bitmap Heap Scan on cards  (cost=253.16..3211.84 rows=1618 width=22) (actual time=0.556..1.110 rows=109 loops=1)
                        Recheck Cond: ((lower((name)::text) ~~ '%glurak%'::text) OR ('glurak'::text <% lower((name)::text)))
                        Filter: ((external_id IS NOT NULL) AND ((lower((name)::text) ~~ '%glurak%'::text) OR ('glurak'::text <% lower((name)::text))))
                        Heap Blocks: exact=94

## 'リザードン': 5 ms
    Limit  (cost=280.57..280.61 rows=16 width=13) (actual time=1.794..1.799 rows=30 loops=1)
      Buffers: shared hit=171
      ->  Sort  (cost=280.57..280.61 rows=16 width=13) (actual time=1.792..1.795 rows=30 loops=1)
            Sort Key: (max(word_similarity('リザードン'::text, lower((name)::text)))) DESC
            Sort Method: top-N heapsort  Memory: 26kB
            Buffers: shared hit=171
            ->  GroupAggregate  (cost=279.89..280.25 rows=16 width=13) (actual time=1.036..1.751 rows=150 loops=1)
                  Group Key: external_id
                  Buffers: shared hit=171
                  ->  Sort  (cost=279.89..279.93 rows=16 width=22) (actual time=1.026..1.037 rows=150 loops=1)
                        Sort Key: external_id
                        Sort Method: quicksort  Memory: 33kB
                        Buffers: shared hit=171
                        ->  Bitmap Heap Scan on cards  (cost=218.41..279.57 rows=16 width=22) (actual time=0.468..0.913 rows=150 loops=1)

## '리자몽': 3 ms
    Limit  (cost=228.76..228.80 rows=16 width=13) (actual time=0.240..0.241 rows=0 loops=1)
      Buffers: shared hit=39
      ->  Sort  (cost=228.76..228.80 rows=16 width=13) (actual time=0.239..0.240 rows=0 loops=1)
            Sort Key: (max(word_similarity('리자몽'::text, lower((name)::text)))) DESC
            Sort Method: quicksort  Memory: 25kB
            Buffers: shared hit=39
            ->  GroupAggregate  (cost=228.08..228.44 rows=16 width=13) (actual time=0.230..0.231 rows=0 loops=1)
                  Group Key: external_id
                  Buffers: shared hit=39
                  ->  Sort  (cost=228.08..228.12 rows=16 width=22) (actual time=0.229..0.230 rows=0 loops=1)
                        Sort Key: external_id
                        Sort Method: quicksort  Memory: 25kB
                        Buffers: shared hit=39
                        ->  Bitmap Heap Scan on cards  (cost=166.60..227.76 rows=16 width=22) (actual time=0.221..0.221 rows=0 loops=1)

## '噴火龍': 4 ms
    Limit  (cost=228.76..228.80 rows=16 width=13) (actual time=0.662..0.667 rows=30 loops=1)
      Buffers: shared hit=97
      ->  Sort  (cost=228.76..228.80 rows=16 width=13) (actual time=0.661..0.663 rows=30 loops=1)
            Sort Key: (max(word_similarity('噴火龍'::text, lower((name)::text)))) DESC
            Sort Method: top-N heapsort  Memory: 26kB
            Buffers: shared hit=97
            ->  GroupAggregate  (cost=228.08..228.44 rows=16 width=13) (actual time=0.488..0.637 rows=61 loops=1)
                  Group Key: external_id
                  Buffers: shared hit=97
                  ->  Sort  (cost=228.08..228.12 rows=16 width=22) (actual time=0.476..0.481 rows=61 loops=1)
                        Sort Key: external_id
                        Sort Method: quicksort  Memory: 28kB
                        Buffers: shared hit=97
                        ->  Bitmap Heap Scan on cards  (cost=166.60..227.76 rows=16 width=22) (actual time=0.220..0.426 rows=61 loops=1)

## '喷火龙': 2 ms
    Limit  (cost=228.76..228.80 rows=16 width=13) (actual time=0.227..0.228 rows=1 loops=1)
      Buffers: shared hit=40
      ->  Sort  (cost=228.76..228.80 rows=16 width=13) (actual time=0.225..0.226 rows=1 loops=1)
            Sort Key: (max(word_similarity('喷火龙'::text, lower((name)::text)))) DESC
            Sort Method: quicksort  Memory: 25kB
            Buffers: shared hit=40
            ->  GroupAggregate  (cost=228.08..228.44 rows=16 width=13) (actual time=0.217..0.218 rows=1 loops=1)
                  Group Key: external_id
                  Buffers: shared hit=40
                  ->  Sort  (cost=228.08..228.12 rows=16 width=22) (actual time=0.210..0.211 rows=1 loops=1)
                        Sort Key: external_id
                        Sort Method: quicksort  Memory: 25kB
                        Buffers: shared hit=40
                        ->  Bitmap Heap Scan on cards  (cost=166.60..227.76 rows=16 width=22) (actual time=0.200..0.201 rows=1 loops=1)
