SELECT LOWER(HEX(id)) AS id, LOWER(HEX(parent_id)) AS parent_id
FROM category
WHERE parent_id IS NULL;

