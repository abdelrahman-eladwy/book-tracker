// Runs once, the first time the MongoDB data volume is created
// (mounted into /docker-entrypoint-initdb.d by the Jenkins pipeline).
// Creates the application user with readWrite access to the app database only,
// so Django never connects as the root user.
const dbName = process.env.MONGO_INITDB_DATABASE || "book_tracker";

db.getSiblingDB(dbName).createUser({
  user: process.env.MONGO_APP_USER,
  pwd: process.env.MONGO_APP_PASSWORD,
  roles: [{ role: "readWrite", db: dbName }],
});
