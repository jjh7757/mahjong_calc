// ankan_1m 차이 확인: 안깡이 있는 11장 손의 이페코를 원본이 보는지.
package main

import (
	"fmt"

	"github.com/EndlessCheng/mahjong-helper/util"
	"github.com/EndlessCheng/mahjong-helper/util/model"
)

func main() {
	for _, h := range []string{"234p 789789s 55z", "234p 789789s 55z 111m"} {
		pi := &model.PlayerInfo{HandTiles34: util.MustStrToTiles34(h), WinTile: 24, RoundWindTile: 27, SelfWindTile: 27, NumRedFives: []int{0, 0, 0}}
		if len(h) < 20 {
			pi.Melds = []model.Meld{{MeldType: model.MeldTypeAnkan, Tiles: []int{0, 0, 0, 0}}}
		}
		for _, d := range util.DivideTiles34(pi.HandTiles34) {
			fmt.Printf("%s: %+v\n", h, *d)
		}
		r := util.CalcPoint(pi)
		fmt.Println(h, "point", r.Point)
	}
}
