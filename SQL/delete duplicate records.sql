SELECT m1.*
FROM manifest m1
JOIN manifest m2 ON m1.itemid = m2.itemid
WHERE m1.id <> m2.id
ORDER BY m1.itemid;