package models

import "gorm.io/gorm"

type HostMapping struct {
	gorm.Model
	ID      uint `gorm:"primaryKey"`
	IndexID uint
	Host    string
}
