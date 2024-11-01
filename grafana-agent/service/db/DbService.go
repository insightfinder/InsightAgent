package db

import (
	"database/sql"
	"fmt"
	_ "github.com/marcboeker/go-duckdb"
	"log/slog"
	"time"
)

type DbService struct {
	Db *sql.DB
}

func (dbSvc *DbService) CloseDbService() {
	err := dbSvc.Db.Close()
	if err != nil {
		slog.Error("Failed to close the database connection:", err)
	}
}

func (dbSvc *DbService) CreateTable(projectName string) {
	createTableSql := fmt.Sprintf(`
		CREATE TABLE IF NOT EXISTS %s (
			timestamp TIMESTAMP,
			instance VARCHAR,
			container VARCHAR,
			component VARCHAR,
			metricName VARCHAR,
			metricValue FLOAT
		);
	`, getTableName(projectName))
	_, err := dbSvc.Db.Exec(createTableSql)
	if err != nil {
		slog.Error("Failed to create table:", err)
	}
	slog.Info("Table %s{} created successfully.", projectName)
}

func CreateDbService() *DbService {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		slog.Error("Failed to connect to DuckDB:", err)
	}

	return &DbService{Db: db}
}

func (dbSvc *DbService) SaveMetrics(project string, timestamp time.Time, instance, container, component string, metricName string, metricValue float64) error {
	// Prepare the insert statement
	insertQuery := fmt.Sprintf(`INSERT INTO %s (timestamp, instance, container,component, metricName, metricValue) VALUES (?, ?, ?, ?,?, ?);`, getTableName(project))
	_, err := dbSvc.Db.Exec(insertQuery, timestamp, instance, container, component, metricName, metricValue)
	if err != nil {
		slog.Error("Failed to insert data:", err)
	}
	return err
}

func (dbSvc *DbService) GetUniqueInstances(project string) *[]*InstanceContainerPair {
	// Result
	var result []*InstanceContainerPair

	// Prepare the select statement
	selectQuery := fmt.Sprintf(`SELECT 
						distinct instance, container
					FROM 
						%s;`, getTableName(project))
	rows, err := dbSvc.Db.Query(selectQuery)
	if err != nil {
		slog.Error("Failed to select data:", err)
	}
	defer rows.Close()

	for rows.Next() {
		var instance string
		var container string
		err := rows.Scan(&instance, &container)
		if err != nil {
			slog.Error("Failed to scan data:", err)
		}
		result = append(result, &InstanceContainerPair{instance, container})
	}

	return &result
}

func (dbSvc *DbService) GetComponentName(project, instance, container string) string {

	// Prepare the select statement
	selectQuery := fmt.Sprintf(`SELECT component FROM %s WHERE instance = ? AND container = ? LIMIT 1;`, getTableName(project))
	rows, err := dbSvc.Db.Query(selectQuery, instance, container)
	if err != nil {
		slog.Error("Failed to select data:", err)
	}
	defer rows.Close()

	for rows.Next() {
		var component string
		err := rows.Scan(&component)
		if err != nil {
			slog.Error("Failed to scan data:", err)
		}
		return component
	}
	return ""
}

func (dbSvc *DbService) GetUniqueTimestamps(project string, instance, container string) *[]time.Time {

	var result []time.Time

	// Prepare the select statement
	selectQuery := fmt.Sprintf(`SELECT distinct timestamp FROM %s WHERE instance = ? AND container = ?;`, getTableName(project))
	rows, err := dbSvc.Db.Query(selectQuery, instance, container)
	if err != nil {
		slog.Error("Failed to select data:", err)
	}
	defer rows.Close()

	for rows.Next() {
		var timestamp time.Time
		err := rows.Scan(&timestamp)
		if err != nil {
			slog.Error("Failed to scan data:", err)
		}
		result = append(result, timestamp)
	}

	return &result
}

func (dbSvc *DbService) GetMetrics(project string, timestamp time.Time, instance, container string) *[]MetricNameValuePair {
	result := make([]MetricNameValuePair, 0)

	// Prepare the select statement
	selectQuery := fmt.Sprintf(`SELECT timestamp, metricName, metricValue FROM %s WHERE timestamp = ? AND instance = ? AND container = ?;`, getTableName(project))
	rows, err := dbSvc.Db.Query(selectQuery, timestamp, instance, container)
	if err != nil {
		slog.Error("Failed to select data:", err)
	}
	defer rows.Close()

	for rows.Next() {
		var timestamp time.Time
		var metricName string
		var metricValue float64
		err := rows.Scan(&timestamp, &metricName, &metricValue)
		if err != nil {
			slog.Error("Failed to scan data:", err)
		}
		result = append(result, MetricNameValuePair{timestamp, metricName, metricValue})
	}

	return &result

}
func (dbSvc *DbService) DebugTable(project string) {
	// Prepare the select statement
	selectQuery := fmt.Sprintf(`SELECT * FROM ;`, getTableName(project))
	rows, err := dbSvc.Db.Query(selectQuery)
	if err != nil {
		slog.Error("Failed to select data:", err)
	}
	defer rows.Close()

	for rows.Next() {
		var timestamp time.Time
		var instance string
		var container string
		var component string
		var metricName string
		var metricValue float64
		err := rows.Scan(&timestamp, &instance, &container, &component, &metricName, &metricValue)
		if err != nil {
			slog.Error("Failed to scan data:", err)
		}
		slog.Info("DebugTable", "Values", timestamp, instance, container, component, metricName, metricValue)
	}
}
