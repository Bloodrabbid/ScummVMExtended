/* ScummVM - Graphic Adventure Engine
 *
 * ScummVM is the legal property of its developers, whose names
 * are too numerous to list here. Please refer to the COPYRIGHT
 * file distributed with this source distribution.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

#ifndef STARK_MOVEMENT_DIRECT_WALK_H
#define STARK_MOVEMENT_DIRECT_WALK_H

#include "engines/stark/movement/movement.h"

namespace Stark {

namespace Resources {
class FloorPositionedItem;
}

/**
 * Make an item walk in a camera relative direction on the current
 * location's floor, without a destination.
 *
 * Used for controlling the player character directly with a gamepad
 * analog stick. The movement lasts as long as the input vector is
 * non null, and stops when the stick is released.
 */
class DirectWalk : public Movement {
public:
	DirectWalk(Resources::FloorPositionedItem *item);
	virtual ~DirectWalk();

	// Movement API
	void start() override;
	void stop(bool force = false) override;
	void onGameLoop() override;
	uint32 getType() const override;
	void saveLoad(ResourceSerializer *serializer) override;

	/**
	 * Set the input vector in camera space.
	 *
	 * x is positive towards the right of the screen, y is positive
	 * towards the bottom. The vector magnitude must be in the 0..1
	 * range. Deflections greater than the run threshold make the
	 * character run.
	 */
	void setInputVector(float x, float y);

private:
	static const float _runThreshold;

	float getAngularSpeed() const;
	float computeDistancePerGameLoop() const;
	void changeItemAnim();

	Resources::FloorPositionedItem *_item3D;

	float _inputX, _inputY;
	bool _running;
	TurnDirection _turnDirection;
};

} // End of namespace Stark

#endif // STARK_MOVEMENT_DIRECT_WALK_H
