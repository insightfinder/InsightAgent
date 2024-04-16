package models

type HostMapping struct {
	ID      uint `gorm:"primaryKey"`
	IndexID int  `gorm:"unique"`
	Host    string
}
