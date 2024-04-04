package models

type HostMapping struct {
	ID      uint `gorm:"primaryKey"`
	IndexID uint `gorm:"unique"`
	Host    string
}
